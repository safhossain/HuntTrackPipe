import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from './views/DashboardView.vue'
import NewApplicationView from './views/NewApplicationView.vue'
import SessionView from './views/SessionView.vue'
import ConvertView from './views/ConvertView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView },
    { path: '/new', name: 'new', component: NewApplicationView },
    { path: '/convert', name: 'convert', component: ConvertView },
    { path: '/sessions/:folder', name: 'session', component: SessionView, props: true },
  ],
})
