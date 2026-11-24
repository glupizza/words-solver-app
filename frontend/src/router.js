import { createRouter, createWebHistory } from 'vue-router'
import Home from './components/Home.vue'
import Admin from './components/Admin.vue'

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/admin', component: Admin },
  { path: '/admin/rejected', component: Admin },
  { path: '/admin/solver', component: Home },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
