/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './opol/app/templates/**/*.html',  
    './opol/app/static/**/*.css',   
  ],
  theme: {
    extend: {},
  },
  plugins: [],
  darkMode: 'class',
}


// Here you go:
// npx tailwindcss -i ./opol/app/static/input.css -o ./opol/app/static/output.css --watch
