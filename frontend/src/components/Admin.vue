<template>
  <main class="admin-page">
    <section class="admin-card" :class="{ 'admin-card-wide': authenticated && rejectedPage }">
      <header class="admin-header">
        <span class="admin-eyebrow">Worder · управление</span>
        <h1>{{ rejectedPage ? 'Исключённые слова' : 'Администрирование' }}</h1>
        <p>{{ rejectedPage ? 'Слова, которые не принимаются игрой' : 'Управление словарём Worder' }}</p>
      </header>

      <p v-if="loading" class="admin-status" role="status">Проверяем сессию…</p>
      <template v-else-if="!authenticated">
        <template v-if="rejectedPage">
          <p class="admin-status">Для просмотра списка необходимо войти.</p>
          <router-link class="admin-button admin-button-primary" to="/admin">Войти</router-link>
        </template>
        <form v-else class="login-form" @submit.prevent="login">
          <label for="admin-password">Пароль администратора</label>
          <input id="admin-password" v-model="password" type="password" autocomplete="current-password" required />
          <button class="admin-button admin-button-primary" type="submit" :disabled="busy">{{ busy ? 'Входим…' : 'Войти' }}</button>
        </form>
      </template>
      <template v-else>
        <template v-if="!rejectedPage">
          <nav class="admin-menu" aria-label="Управление">
            <router-link class="menu-action" to="/admin/solver">
              <span><strong>Открыть Worder</strong><small>Решатель с возможностью исключать слова</small></span><span aria-hidden="true">→</span>
            </router-link>
            <router-link class="menu-action" to="/admin/rejected">
              <span><strong>Исключённые слова</strong><small>Просмотр, поиск и восстановление</small></span><span aria-hidden="true">→</span>
            </router-link>
          </nav>
          <button class="admin-button admin-button-secondary logout-menu" type="button" :disabled="busy" @click="logout">Выйти</button>
        </template>
        <template v-else>
          <div class="rejected-heading"><span class="total-badge">Всего: {{ total }}</span></div>
          <nav class="admin-nav" aria-label="Управление">
            <router-link class="admin-button admin-button-secondary" to="/admin/solver">Открыть Worder</router-link>
            <router-link class="admin-button admin-button-secondary" to="/admin">Управление</router-link>
            <button class="admin-button admin-button-secondary" type="button" :disabled="busy" @click="logout">Выйти</button>
          </nav>
          <div class="list-actions">
            <label class="search-field" for="rejected-search"><span>Поиск по слову</span><input id="rejected-search" v-model="search" type="search" placeholder="Найти слово" @input="scheduleSearch" /></label>
            <a class="admin-button admin-button-secondary export-button" href="/api/admin/rejected/export" download>Экспорт TXT</a>
          </div>
          <div v-if="!words.length && !error" class="empty-list">
            {{ search.trim() || total > 0 ? 'По вашему запросу ничего не найдено' : 'Исключённых слов пока нет' }}
          </div>
          <ul v-else class="rejected-list">
            <li v-for="item in words" :key="item.word">
              <span class="word-info"><strong>{{ item.word }}</strong><small>{{ formatDate(item.rejected_at) }}</small></span>
              <button class="admin-button admin-button-secondary" type="button" :disabled="busy" @click="restore(item.word)">Вернуть</button>
            </li>
          </ul>
          <div v-if="matched > 50 || page > 1" class="pagination">
            <button class="admin-button admin-button-secondary" type="button" :disabled="page === 1 || busy" @click="changePage(-1)">Назад</button>
            <span>Страница {{ page }}</span>
            <button class="admin-button admin-button-secondary" type="button" :disabled="page * 50 >= matched || busy" @click="changePage(1)">Далее</button>
          </div>
        </template>
      </template>
      <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    </section>
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
.admin-page { width: min(100%, 820px); margin: 0 auto; padding: 36px 16px calc(32px + env(safe-area-inset-bottom, 0px)); }
.admin-card { width: min(100%, 480px); margin: 0 auto; padding: clamp(22px, 5vw, 36px); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); box-shadow: 0 14px 36px rgba(36, 52, 71, .12); }
.admin-card-wide { width: 100%; }
.admin-header { margin-bottom: 26px; }
.admin-eyebrow { color: var(--color-warm); font-size: .75rem; font-weight: 800; letter-spacing: .09em; text-transform: uppercase; }
.admin-header h1 { margin: 8px 0 4px; color: var(--text); font-size: clamp(1.5rem, 5vw, 2rem); line-height: 1.2; overflow-wrap: anywhere; }
.admin-header p, .admin-status { margin: 0; color: var(--muted); }
.login-form { display: grid; gap: 10px; }
.login-form label, .search-field span { color: var(--text); font-size: .9rem; font-weight: 700; }
.login-form input, .search-field input { width: 100%; min-width: 0; min-height: 48px; padding: 11px 13px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-light); color: var(--text); font-size: 16px; }
.login-form .admin-button { width: 100%; margin-top: 8px; }
.admin-button { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; padding: 10px 16px; border: 1px solid var(--border); border-radius: 10px; font-weight: 700; line-height: 1.2; text-align: center; text-decoration: none; cursor: pointer; transition: background .15s, border-color .15s; }
.admin-button-primary { border-color: var(--accent); background: var(--accent); color: #fff; }
.admin-button-primary:hover { background: var(--accent-hover); }
.admin-button-secondary { background: var(--surface-light); color: var(--accent-hover); }
.admin-button-secondary:hover, .menu-action:hover { border-color: var(--accent); background: #e8eef3; }
.admin-button:disabled { cursor: not-allowed; opacity: .55; }
.admin-page :is(a, button, input):focus-visible { outline: 3px solid var(--color-warm); outline-offset: 2px; }
.admin-menu { display: grid; gap: 10px; }
.menu-action { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 76px; padding: 15px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-light); color: var(--text); text-decoration: none; }
.menu-action strong, .menu-action small { display: block; }
.menu-action small { margin-top: 4px; color: var(--muted); font-size: .82rem; }
.menu-action > span:last-child { color: var(--accent); font-size: 1.3rem; }
.logout-menu { margin-top: 20px; }
.rejected-heading { margin-bottom: 16px; }
.total-badge { display: inline-block; padding: 5px 10px; border-radius: 999px; background: var(--surface-light); color: var(--accent-hover); font-size: .85rem; font-weight: 800; }
.admin-nav { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.list-actions { display: flex; align-items: end; gap: 10px; }
.search-field { display: grid; flex: 1; min-width: 0; gap: 7px; }
.export-button { min-height: 48px; }
.rejected-list { margin: 18px 0 0; padding: 0; list-style: none; }
.rejected-list li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 0; border-bottom: 1px solid var(--border); }
.word-info { min-width: 0; overflow-wrap: anywhere; }
.word-info strong, .word-info small { display: block; }
.word-info small { margin-top: 3px; color: var(--muted); }
.empty-list { margin-top: 20px; padding: 24px 16px; border: 1px dashed var(--border); border-radius: 12px; background: var(--surface-light); color: var(--muted); text-align: center; }
.pagination { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-top: 20px; color: var(--muted); font-size: .9rem; }
.admin-error { margin: 18px 0 0; padding: 12px; border: 1px solid #d7c5bd; border-radius: 10px; background: #f8f3f0; color: #6e4740; overflow-wrap: anywhere; }
@media (max-width: 480px) { .admin-page { padding-top: 16px; } .list-actions { align-items: stretch; flex-direction: column; } .admin-nav .admin-button { flex: 1 1 auto; } }
</style>
