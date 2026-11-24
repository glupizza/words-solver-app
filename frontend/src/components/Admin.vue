<template>
  <main class="admin-page">
    <h1>{{ rejectedPage ? 'Исключённые слова' : 'Администрирование' }}</h1>
    <p v-if="loading">Проверяем сессию…</p>
    <template v-else-if="!authenticated">
      <p v-if="rejectedPage">Для просмотра списка необходимо войти.</p>
      <router-link v-if="rejectedPage" to="/admin">Войти</router-link>
      <form v-else @submit.prevent="login">
        <label>Пароль <input v-model="password" type="password" autocomplete="current-password" required /></label>
        <button :disabled="busy">Войти</button>
      </form>
    </template>
    <template v-else>
      <nav class="admin-nav">
        <router-link to="/admin/solver">Открыть Worder с редактированием</router-link>
        <router-link v-if="!rejectedPage" to="/admin/rejected">Исключённые слова</router-link>
        <button :disabled="busy" @click="logout">Выйти</button>
      </nav>
      <template v-if="rejectedPage">
        <p>Всего: {{ total }}</p>
        <label>Поиск <input v-model="search" type="search" @input="scheduleSearch" /></label>
        <a href="/api/admin/rejected/export" download>Экспорт TXT</a>
        <p v-if="!words.length && !search">Исключённых слов пока нет</p>
        <ul class="rejected-list">
          <li v-for="item in words" :key="item.word">
            <span>{{ item.word }}<br /><small>{{ formatDate(item.rejected_at) }}</small></span>
            <button :disabled="busy" @click="restore(item.word)">Вернуть</button>
          </li>
        </ul>
        <div v-if="matched > 50 || page > 1">
          <button :disabled="page === 1 || busy" @click="changePage(-1)">Назад</button>
          <span> {{ page }} </span>
          <button :disabled="page * 50 >= matched || busy" @click="changePage(1)">Далее</button>
        </div>
      </template>
    </template>
    <p v-if="error" role="alert">{{ error }}</p>
  </main>
</template>
<script>
import { session, adminRequest } from '../adminApi.js';
export default {
  data() { return { authenticated: false, loading: true, busy: false, password: '', error: '', words: [], total: 0, matched: 0, page: 1, search: '', timer: null }; },
  computed: { rejectedPage() { return this.$route.path === '/admin/rejected'; } },
  watch: { '$route.path'() { if (this.authenticated && this.rejectedPage) this.load(); } },
  async mounted() { try { this.authenticated = await session(); if (this.authenticated && this.rejectedPage) await this.load(); } catch (error) { this.error = error.message; } finally { this.loading = false; } },
  beforeUnmount() { clearTimeout(this.timer); },
  methods: {
    async login() { if (this.busy) return; this.busy = true; this.error = ''; try { await adminRequest('login', { password: this.password }); this.password = ''; this.authenticated = true; } catch (error) { this.error = error.message; } finally { this.busy = false; } },
    async logout() { if (this.busy) return; this.busy = true; try { await adminRequest('logout', {}); this.authenticated = false; this.words = []; this.$router.push('/admin'); } catch (error) { this.error = error.message; } finally { this.busy = false; } },
    async load() { try { const data = await adminRequest(`rejected?search=${encodeURIComponent(this.search)}&page=${this.page}`); this.words = data.words; this.total = data.total; this.matched = data.matched; } catch (error) { this.error = error.message; this.words = []; } },
    scheduleSearch() { clearTimeout(this.timer); this.timer = setTimeout(() => { this.page = 1; this.load(); }, 250); },
    async restore(word) { if (this.busy) return; this.busy = true; this.error = ''; try { await adminRequest('rejected/restore', { word }); try { const saved = JSON.parse(sessionStorage.getItem('worder-results') || 'null'); if (saved?.state?.hiddenWords) { saved.state.hiddenWords = saved.state.hiddenWords.filter((item) => item !== word); sessionStorage.setItem('worder-results', JSON.stringify(saved)); } } catch (_error) { /* Storage is optional. */ } await this.load(); } catch (error) { this.error = error.message; } finally { this.busy = false; } },
    changePage(delta) { this.page += delta; this.load(); },
    formatDate(date) { return new Date(date).toLocaleString('ru-RU'); },
  },
};
</script>
<style scoped>
.admin-page { max-width: 700px; margin: auto; padding: 20px; }
.admin-nav { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin-bottom: 24px; }
input { max-width: 100%; padding: 10px; }
button { padding: 10px; }
.rejected-list { list-style: none; padding: 0; }
.rejected-list li { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid #ddd; }
</style>
