import React from "react";
import ReactDOM from "react-dom/client";
import { ChakraProvider, ColorModeScript, extendTheme } from "@chakra-ui/react";
import App from "./App";

const theme = extendTheme({
  config: {
    initialColorMode: "dark",
    useSystemColorMode: false
  },
  colors: {
    brand: {
      50: "#ffe4ed",
      100: "#fbb7cd",
      200: "#f489ad",
      300: "#ee5c8c",
      400: "#e8306c",
      500: "#cf1853",
      600: "#a11040",
      700: "#72092d",
      800: "#44031a",
      900: "#1a0009"
    }
  },
  semanticTokens: {
    colors: {
      surface: { default: "#141b2f" },
      surfaceMuted: { default: "#0f1628" },
      surfaceAlt: { default: "#1d2540" },
      textPrimary: { default: "#f8fafc" },
      textSecondary: { default: "#93a4c3" },
      accent: { default: "#e8306c" },
      backgroundGradientStart: { default: "#070c18" },
      backgroundGradientEnd: { default: "#131b33" }
    }
  },
  styles: {
    global: {
      body: {
        bg: "linear-gradient(120deg, var(--chakra-colors-backgroundGradientStart) 0%, var(--chakra-colors-backgroundGradientEnd) 100%)",
        color: "textPrimary"
      }
    }
  }
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ChakraProvider theme={theme}>
      <ColorModeScript initialColorMode={theme.config.initialColorMode} />
      <App />
    </ChakraProvider>
  </React.StrictMode>
);

