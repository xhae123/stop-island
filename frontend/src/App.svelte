<script>
  import Router from 'svelte-spa-router'
  import Main from './routes/Main.svelte'
  import Menu from './routes/Menu.svelte'
  import Verify from './routes/Verify.svelte'
  import Reserve from './routes/Reserve.svelte'
  import Guestbook from './routes/Guestbook.svelte'

  const routes = {
    '/': Main,
    '/menu': Menu,
    '/verify': Verify,
    '/reserve': Reserve,
    '/guestbook': Guestbook,
  }
</script>

<main class="min-h-screen bg-white">
  <Router {routes} />
</main>
