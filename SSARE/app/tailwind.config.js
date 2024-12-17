/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './SSARE/app/templates/**/*.html',  
    './SSARE/app/static/**/*.css',   
  ],
  theme: {
    extend: {},
  },
  plugins: [],
  darkMode: 'class',
}


// Here you go:
// npx tailwindcss -i ./SSARE/app/static/input.css -o ./SSARE/app/static/output.css --watch
