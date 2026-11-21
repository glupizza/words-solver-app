import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { installGrailDebug } from './grailDebug'


const app = createApp(App)
installGrailDebug(app, window, document)
app.use(router)
    .mount('#app')

