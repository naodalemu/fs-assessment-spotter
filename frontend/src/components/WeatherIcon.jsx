import {
  AcUnit as SnowIcon,
  Cloud as CloudIcon,
  FilterDrama as PartlyCloudyIcon,
  Thunderstorm as StormIcon,
  Umbrella as RainIcon,
  WbSunny as SunIcon,
  Foggy as FogIcon,
} from '@mui/icons-material';

const ICONS = [
  [/thunder|storm/i, StormIcon],
  [/snow|blizzard/i, SnowIcon],
  [/rain|drizzle|shower/i, RainIcon],
  [/fog/i, FogIcon],
  [/partly|mainly/i, PartlyCloudyIcon],
  [/overcast|cloud/i, CloudIcon],
];

/** Icon matching a weather description ("Light rain", "Clear sky", …). */
function WeatherIcon({ description = '', ...props }) {
  const Icon = ICONS.find(([pattern]) => pattern.test(description))?.[1] ?? SunIcon;
  return <Icon aria-hidden {...props} />;
}

export default WeatherIcon;
