/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./web_viewer/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: "#7f0df2",
        "background-light": "#f7f5f8",
        "background-dark": "#121212",
        "surface-glass": "rgba(255, 255, 255, 0.03)",
        "surface-glass-hover": "rgba(255, 255, 255, 0.07)",
        "border-glass": "rgba(255, 255, 255, 0.08)",
      },
      fontFamily: {
        display: ["Spline Sans", "sans-serif"],
        body: ["Inter", "sans-serif"],
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/container-queries'),
  ],
};
