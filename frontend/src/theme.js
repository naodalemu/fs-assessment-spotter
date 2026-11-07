import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#5fdede',
      light: '#8effff',
      dark: '#28abab',
      contrastText: '#043344',
    },
    secondary: {
      main: '#043344',
      light: '#0d4a5e',
      dark: '#021e28',
      contrastText: '#fafbfa',
    },
    background: {
      default: '#0d1116',
      paper: '#1c2227',
      darkNavy: '#043344',
      cardActive: '#282b33',
    },
    text: {
      primary: '#fafbfa',
      secondary: 'rgba(250, 251, 250, 0.68)',
      disabled: 'rgba(250, 251, 250, 0.38)',
    },
    success: { main: '#66bb6a' },
    warning: { main: '#ffa726' },
    error: { main: '#ef5350' },
  },
  typography: {
    fontFamily: '"DM Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    h5: {
      fontWeight: 700,
    },
    h6: {
      fontWeight: 600,
    },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          textTransform: 'none',
          fontWeight: 600,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          background: '#1c2227',
          backgroundImage: 'none',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        variant: 'outlined',
        size: 'small',
      },
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          background: '#161a20',
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(255, 255, 255, 0.12)',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(95, 222, 222, 0.5)',
          },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: '#5fdede',
            borderWidth: '1.5px',
          },
        },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderColor: 'rgba(255, 255, 255, 0.08)',
          fontSize: '0.8rem',
        },
        stickyHeader: {
          backgroundColor: '#0d1116',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          fontWeight: 600,
        },
      },
    },
  },
});

export default theme;
