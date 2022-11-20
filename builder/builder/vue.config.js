const { defineConfig } = require('@vue/cli-service')
module.exports = {
  ...defineConfig({
    transpileDependencies: true
  }),
  // Путь куда будет собран(build) `index.html`
  outputDir: './dist_vue',
  // Пути для статических файлов в итоговом index.html, если использовать локально, то уставить `./`, если через сервер, то удалить этот параметр 
  publicPath: './',
}