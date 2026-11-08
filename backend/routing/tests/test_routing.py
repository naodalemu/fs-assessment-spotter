"""
Tests for the routing service: ORS integration (mocked), alternative-route
selection, geometry clean-up and the simulated fallback.
"""

from unittest.mock import MagicMock, patch

import polyline
import pytest
import requests

from routing.services import routing
from routing.services.routing import (
    Route,
    _overlap,
    _select_distinct,
    _via_point,
    generate_mock_routes,
    get_routes,
    RoutingUnavailable,
    is_placeholder_key,
    remove_loops,
    simplify,
)

DALLAS = (32.7767, -96.7970)
CHICAGO = (41.8781, -87.6298)


def _line(lat1, lng1, lat2, lng2, n=50):
    return [[lat1 + (lat2 - lat1) * i / (n - 1), lng1 + (lng2 - lng1) * i / (n - 1)] for i in range(n)]


def _ors_response(geometries, distance_m=1_600_000, duration_s=54_000):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "routes": [
            {"summary": {"distance": distance_m, "duration": duration_s}, "geometry": polyline.encode(g)}
            for g in geometries
        ]
    }
    return resp


class TestPlaceholderKeyDetection:
    @pytest.mark.parametrize("key", ["your_openrouteservice_api_key_here", "", None, "   ", "PLACEHOLDER", "changeme"])
    def test_placeholders(self, key):
        assert is_placeholder_key(key) is True

    def test_real_key(self):
        assert is_placeholder_key("5b3ce3597851110001cf62483849") is False


class TestGeometryHelpers:
    def test_remove_loops_cuts_out_and_back_spur(self):
        main = _line(35.0, -97.0, 35.0, -96.0, 60)
        spur_out = _line(35.0, -96.5, 35.1, -96.5, 20)  # ~7 mi north of the road
        # Drive half the road, go up the spur and come back, continue
        path = main[:30] + spur_out[1:] + spur_out[::-1][1:] + main[30:]
        cleaned = remove_loops(path)
        # Only a stub shorter than the 0.5-mile minimum loop may remain (spur was ~7 mi)
        assert max(p[0] for p in cleaned) < 35.01
        assert len(cleaned) <= len(main) + 5

    def test_remove_loops_keeps_straight_road(self):
        main = _line(35.0, -97.0, 36.0, -96.0, 200)
        assert remove_loops(main) == main

    def test_simplify_keeps_endpoints_and_drops_collinear(self):
        line = _line(35.0, -97.0, 36.0, -96.0, 500)
        out = simplify(line)
        assert out[0] == line[0] and out[-1] == line[-1]
        assert len(out) == 2

    def test_overlap(self):
        a = _line(35.0, -97.0, 35.0, -90.0)
        b = _line(35.01, -97.0, 35.01, -90.0)
        c = _line(37.0, -97.0, 37.0, -90.0)
        assert _overlap(a, b) == 1.0
        assert _overlap(a, c) == 0.0

    def test_via_point_is_beside_midpoint(self):
        lat, lng = _via_point((35.0, -100.0), (35.0, -90.0), 0.2)
        assert lng == pytest.approx(-95.0, abs=0.01)
        assert lat > 35.5  # offset north of an east-west trip

    def test_select_distinct_drops_duplicates_and_long_detours(self):
        fast = Route(_line(35.0, -97.0, 35.0, -90.0), 400, 6.0)
        duplicate = Route(_line(35.01, -97.0, 35.01, -90.0), 405, 6.1)
        north = Route(_line(35.0, -97.0, 37.0, -90.0), 430, 6.8)
        absurd = Route(_line(35.0, -97.0, 30.0, -90.0), 700, 11.0)
        assert _select_distinct([absurd, north, duplicate, fast]) == [fast, north]


@pytest.fixture(autouse=True)
def _empty_route_cache():
    routing._route_cache.clear()
    yield
    routing._route_cache.clear()


class TestGetRoutes:
    @patch.object(routing, "settings")
    def test_placeholder_key_uses_simulated_routes(self, mock_settings):
        mock_settings.ORS_API_KEY = "your_openrouteservice_api_key_here"
        routes = get_routes(DALLAS, CHICAGO)
        assert len(routes) == 3
        assert all(r.source == "simulated" for r in routes)
        assert [r.route_index for r in routes] == [0, 1, 2]

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_network_error_raises_instead_of_inventing_routes(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"
        mock_post.side_effect = requests.ConnectionError("down")
        with pytest.raises(RoutingUnavailable, match="unavailable"):
            get_routes(DALLAS, CHICAGO)

    @pytest.mark.parametrize(
        "status, message",
        [
            (403, "temporarily unavailable"),
            (429, "temporarily unavailable"),
            (401, "temporarily unavailable"),
            (404, "not near a drivable road"),
            (500, "temporarily unavailable"),
        ],
    )
    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_http_errors_give_user_facing_messages(self, mock_settings, mock_post, status, message):
        mock_settings.ORS_API_KEY = "real_key"
        response = requests.Response()
        response.status_code = status
        failing = MagicMock()
        failing.raise_for_status.side_effect = requests.HTTPError(response=response)
        mock_post.return_value = failing
        with pytest.raises(RoutingUnavailable, match=message):
            get_routes(DALLAS, CHICAGO)

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_long_trip_builds_alternatives_from_via_points(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"
        direct = _line(*DALLAS, *CHICAGO)
        mid = ((DALLAS[0] + CHICAGO[0]) / 2, (DALLAS[1] + CHICAGO[1]) / 2)

        def respond(url, json, headers, timeout):
            assert headers["Authorization"] == "real_key"
            assert "alternative_routes" not in json  # > 100 km: ORS would reject it
            coords = json["coordinates"]
            if len(coords) == 2:
                return _ors_response([direct], duration_s=50_000)
            via_lng, via_lat = coords[1]
            g = _line(*DALLAS, via_lat, via_lng, 25) + _line(via_lat, via_lng, *CHICAGO, 25)[1:]
            return _ors_response([g], duration_s=56_000 if via_lat > mid[0] else 58_000)

        mock_post.side_effect = respond
        routes = get_routes(DALLAS, CHICAGO)

        assert len(routes) == 3
        assert mock_post.call_count == 3
        assert all(r.source == "openrouteservice" for r in routes)
        assert [r.travel_time_hours for r in routes] == sorted(r.travel_time_hours for r in routes)
        assert routes[0].geometry[0] == pytest.approx(list(DALLAS), abs=1e-5)
        assert len(routes[0].geometry) == len(direct)
        assert routes[0].distance_miles == pytest.approx(994.2, abs=0.5)

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_via_routes_used_when_direct_request_fails(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"

        def respond(url, json, headers, timeout):
            if len(json["coordinates"]) == 2:
                raise requests.Timeout("slow")
            (o_lng, o_lat), (v_lng, v_lat), (d_lng, d_lat) = json["coordinates"]
            return _ors_response([_line(o_lat, o_lng, v_lat, v_lng, 25) + _line(v_lat, v_lng, d_lat, d_lng, 25)[1:]])

        mock_post.side_effect = respond
        routes = get_routes(DALLAS, CHICAGO)
        assert routes and all(r.source == "openrouteservice" for r in routes)

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_results_are_cached(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"
        mock_post.return_value = _ors_response([_line(*DALLAS, *CHICAGO)])
        first = get_routes(DALLAS, CHICAGO)
        calls = mock_post.call_count
        second = get_routes(DALLAS, CHICAGO)
        assert mock_post.call_count == calls
        assert [r.distance_miles for r in first] == [r.distance_miles for r in second]
        assert first[0] is not second[0]

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_short_trip_requests_ors_alternatives(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"
        mock_post.return_value = _ors_response([_line(32.7, -96.8, 32.9, -96.5)])
        get_routes((32.7, -96.8), (32.9, -96.5))
        bodies = [c.kwargs["json"] for c in mock_post.call_args_list]
        assert any("alternative_routes" in b for b in bodies if len(b["coordinates"]) == 2)


class TestUnroutablePoints:
    @staticmethod
    def _no_road(coordinate_index):
        response = requests.Response()
        response.status_code = 404
        response._content = (
            b'{"error":{"code":2010,"message":"Could not find routable point within a radius of '
            b'5000.0 meters of specified coordinate ' + str(coordinate_index).encode() + b': -135.8 63.6."}}'
        )
        failing = MagicMock()
        failing.raise_for_status.side_effect = requests.HTTPError(response=response)
        return failing

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_names_the_origin_even_when_other_requests_fail_differently(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"
        other = requests.Response()
        other.status_code = 400
        other_failing = MagicMock()
        other_failing.raise_for_status.side_effect = requests.HTTPError(response=other)
        # direct request: origin has no road; one via request fails with a different error
        mock_post.side_effect = lambda url, json, headers, timeout: (
            other_failing if len(json["coordinates"]) == 3 and json["coordinates"][1][1] > 40 else self._no_road(0)
        )
        with pytest.raises(RoutingUnavailable, match="the origin is not near a drivable road"):
            get_routes((63.6, -135.8), (25.76, -80.19))

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_names_the_destination(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"
        mock_post.side_effect = lambda url, json, headers, timeout: self._no_road(len(json["coordinates"]) - 1)
        with pytest.raises(RoutingUnavailable, match="the destination is not near a drivable road"):
            get_routes(DALLAS, CHICAGO)

    @patch.object(routing.requests, "post")
    @patch.object(routing, "settings")
    def test_unroutable_via_point_is_not_blamed_on_the_user(self, mock_settings, mock_post):
        mock_settings.ORS_API_KEY = "real_key"
        server_error = requests.Response()
        server_error.status_code = 500
        failing = MagicMock()
        failing.raise_for_status.side_effect = requests.HTTPError(response=server_error)
        # direct request hits a server error; via-point requests fail on the via-point (index 1)
        mock_post.side_effect = lambda url, json, headers, timeout: (
            self._no_road(1) if len(json["coordinates"]) == 3 else failing
        )
        with pytest.raises(RoutingUnavailable) as exc:
            get_routes(DALLAS, CHICAGO)
        assert "origin" not in str(exc.value) and "destination" not in str(exc.value)


class TestMockRoutes:
    def test_three_distinct_routes_between_endpoints(self):
        routes = generate_mock_routes(DALLAS, CHICAGO)
        assert len(routes) == 3
        for route in routes:
            assert route.geometry[0] == [round(DALLAS[0], 6), round(DALLAS[1], 6)]
            assert route.geometry[-1] == [round(CHICAGO[0], 6), round(CHICAGO[1], 6)]
            assert 700 < route.distance_miles < 1300
            assert 10 < route.travel_time_hours < 25
