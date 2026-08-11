/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#F4F1EA",
        ink: {
          DEFAULT: "#2A2C2B",
          light: "#5C5E60",
        },
        status: {
          pass: "#276F4B",
          warning: "#D08C3F",
          review: "#4A55A2",
          fail: "#C83232",
          rejected: "#5C5E60",
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        serif: ['Merriweather', 'serif'],
      },
      boxShadow: {
        'document': '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
      }
    },
  },
  plugins: [],
}
