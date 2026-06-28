/* ═══════════════════════════════════════════════════════
   SpielOS Wizard — Alpine.js component
   8-step setup: welcome → brand → audience → offer → voice
   → examples → connect → done.
   State saved to localStorage for crash recovery.
   ═══════════════════════════════════════════════════════ */

const ICON_RULES = [
  { patterns: ['ai', 'agent', 'automation', 'machine', 'llm', 'gpt', 'model'], icon: 'sparkles' },
  { patterns: ['open', 'source', 'github', 'public', 'repo'], icon: 'git-pull-request' },
  { patterns: ['ship', 'release', 'launch', 'deploy', 'feature', 'build'], icon: 'trending-up' },
  { patterns: ['decision', 'choose', 'picked', 'tradeoff', 'vs'], icon: 'crosshair' },
  { patterns: ['lesson', 'learned', 'takeaway', 'insight'], icon: 'bulb' },
  { patterns: ['failure', 'broke', 'bug', 'fix', 'postmortem'], icon: 'ban' },
  { patterns: ['strategy', 'position', 'plan', 'framework'], icon: 'layers' },
  { patterns: ['client', 'customer', 'case', 'study', 'work'], icon: 'award' },
  { patterns: ['research', 'read', 'study', 'analyzed'], icon: 'feather' },
  { patterns: ['tool', 'script', 'automation', 'stack'], icon: 'cog' },
];

const ICON_SVG = {
  'terminal':       '<rect x="2" y="3" width="20" height="18" rx="2"/><path d="M8 9l4 4-4 4"/><path d="M14 15h4"/>',
  'code':           '<path d="M16 18l6-6-6-6"/><path d="M8 6l-6 6 6 6"/><path d="M12 2l-2 20"/>',
  'cog':            '<circle cx="12" cy="12" r="3"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>',
  'sparkles':       '<path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5z"/><path d="M19 14l1 3 3 1-3 1-1 3-1-3-3-1 3-1z" opacity=".6"/>',
  'arrow-up-right': '<path d="M7 17L17 7"/><path d="M7 7h10v10"/>',
  'panel-left':     '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
  'save':           '<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
  'alert-triangle': '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  'info':           '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  'check-circle':   '<path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/>',
  'refresh-cw':     '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>',
  'trending-up':    '<path d="M23 6l-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/>',
  'crosshair':      '<circle cx="12" cy="12" r="10"/><path d="M12 2v4"/><path d="M12 18v4"/><path d="M2 12h4"/><path d="M18 12h4"/>',
  'bulb':           '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 00-4 12.7V17h8v-2.3A7 7 0 0012 2z"/>',
  'ban':            '<circle cx="12" cy="12" r="10"/><path d="M4.93 4.93l14.14 14.14"/>',
  'layers':         '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
  'award':          '<circle cx="12" cy="8" r="7"/><path d="M8.21 13.89L7 23l5-3 5 3-1.21-9.12"/>',
  'feather':        '<path d="M20.24 12.24a6 6 0 00-8.49-8.49L5 10.5V19h8.5z"/><path d="M16 8L2 22"/><path d="M17.5 15H9"/>',
  'git-pull-request': '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9V6a3 3 0 00-3-3H6"/><path d="M6 15V9"/>',
  'lock':           '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>',
};

function pickIcon(brandName, tagline) {
  const text = `${brandName || ''} ${tagline || ''}`.toLowerCase();
  for (const rule of ICON_RULES) {
    for (const p of rule.patterns) {
      if (text.includes(p)) return rule.icon;
    }
  }
  return 'arrow-up-right';
}

const STORAGE_KEY = 'spielos_wizard_state';

function wizard() {
  return {
    // ── Mode ──
    current: 0,
    saving: false,
    done: false,
    toast: '',
    toastTimer: null,
    target: '',

    // ── Wizard data ──
    doneLines: [],
    installResult: null,

    // ── Wizard state ──
    bufferLoading: false,
    bufferError: '',
    bufferChannels: [],

    steps: [
      { key: 'welcome',  label: 'Welcome' },
      { key: 'brand',    label: 'Brand' },
      { key: 'audience', label: 'Audience' },
      { key: 'offer',    label: 'Offer' },
      { key: 'voice',    label: 'Voice' },
      { key: 'examples', label: 'Examples' },
      { key: 'connect',  label: 'Connect' },
      { key: 'done',     label: 'Done' },
    ],

    form: {
      brand_name: 'YourBrand',
      handle: '@your_handle',
      tagline: '',
      creator_self: '',
      role: '',
      primary_bg: '#000000',
      primary_fg: '#ffffff',
      subtitle_color: '#8a8a8a',
      handle_color: '#505050',
      accent: '#ff6a00',
      title_gradient: false,
      audience_content: '',
      offer_content: '',
      voice_content: '',
      examples_content: '',
      buffer_token: '',
      buffer_channels: [],
      x_api_key: '',
      x_api_secret: '',
      x_access_token: '',
      x_access_secret: '',
      linkedin_access_token: '',
      linkedin_person_urn: '',
      wp_url: '',
      wp_username: '',
      wp_app_password: '',
      devto_api_key: '',
      hashnode_api_key: '',
      hashnode_publication_id: '',
      custom_blog_api_url: '',
      custom_blog_api_method: 'POST',
      custom_blog_api_auth_header: '',
      custom_blog_api_body_template: '{"title":"{{title}}","content":"{{body}}"}',
      custom_blog_mcp_server: '',
      blog_repo: '',
      blog_token: '',
    },

    // ── Computed ──

    get iconKey() {
      return pickIcon(this.form.brand_name, this.form.tagline);
    },

    get iconSvg() {
      const key = this.iconKey;
      const path = ICON_SVG[key] || ICON_SVG['arrow-up-right'];
      return `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${path}</svg>`;
    },

    // ── Init ──

    async init() {
      this.loadState();
      await this.loadSkeletons();
    },

    // ── State persistence ──

    saveState() {
      try {
        const state = {
          current: this.current,
          form: { ...this.form },
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      } catch {}
    },

    loadState() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const state = JSON.parse(raw);
        if (typeof state.current === 'number') {
          this.current = state.current;
        }
        if (state.form) {
          Object.assign(this.form, state.form);
        }
      } catch {}
    },

    // ── Wizard navigation ──

    next() {
      if (this.current < this.steps.length - 1) {
        this.current++;
        this.saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      this.finish();
    },

    back() {
      if (this.current > 0) {
        this.current--;
        this.saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },

    go(i) {
      this.current = i;
      this.saveState();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    closeTab() {
      window.close();
    },

    // ── API calls ──

    async loadSkeletons() {
      try {
        const existing = await Promise.all([
          this.readMaybe('strategy/audience.md'),
          this.readMaybe('strategy/offer.md'),
          this.readMaybe('strategy/voice.md'),
          this.readMaybe('strategy/examples.md'),
        ]);
        const names = ['audience_content', 'offer_content', 'voice_content', 'examples_content'];
        existing.forEach((content, i) => {
          if (content && content.trim()) this.form[names[i]] = content;
        });

        const needsSkeletons = names.some(name => !this.form[name]);
        if (!needsSkeletons) return;
        const r = await fetch('/api/skeletons');
        const data = await r.json();
        for (const name of data.skeletons || []) {
          const res = await fetch(`/api/skeleton/${name}`);
          const payload = await res.json();
          const map = {
            'audience.md': 'audience_content',
            'offer.md': 'offer_content',
            'voice.md': 'voice_content',
            'examples.md': 'examples_content',
          };
          if (map[name] && !this.form[map[name]]) this.form[map[name]] = payload.content || '';
        }
      } catch {}
    },

    async readMaybe(path) {
      try {
        const r = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
        const data = await r.json();
        return data.content || '';
      } catch {
        return '';
      }
    },

    async fetchBufferChannels() {
      if (!this.form.buffer_token) {
        this.bufferError = 'Paste your Buffer access token first.';
        return;
      }
      this.bufferLoading = true;
      this.bufferError = '';
      this.bufferChannels = [];
      try {
        const r = await fetch('/api/buffer/channels', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: this.form.buffer_token }),
        });
        const data = await r.json();
        if (!data.ok) {
          this.bufferError = data.error || 'Buffer rejected the token.';
          this.flash(this.bufferError);
          return;
        }
        this.bufferChannels = data.channels || [];
        this.flash(`Loaded ${this.bufferChannels.length} channels from Buffer.`);
      } catch (e) {
        this.bufferError = 'Could not reach Buffer. Check your network and try again.';
        this.flash(this.bufferError);
      } finally {
        this.bufferLoading = false;
      }
    },

    async finish() {
      this.saving = true;
      try {
        const r = await fetch('/api/finish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.form),
        });
        const data = await r.json();
        if (!data.ok) {
          this.flash(data.error || 'Install failed');
          this.saving = false;
          return;
        }
        this.done = true;
        this.doneLines = (data.written || []).map(f => `${f}  written`);
        this.installResult = data.install || {};
        if (data.install && data.install.errors && data.install.errors.length) {
          this.doneLines.push(`warnings: ${data.install.errors.join(', ')}`);
        }
        this.current = this.steps.length;
        this.saveState();
        this.flash('Installed. Vault is live.');
      } catch (e) {
        this.flash('Install failed: ' + e.message);
      }
      this.saving = false;
    },

    async saveAndQuit() {
      this.saveState();
      this.flash('Progress saved. Run `spiel init` to resume.');
    },

    // ── Helpers ──

    toggle(field, value) {
      if (!Array.isArray(this.form[field])) this.form[field] = [];
      if (!this.form[field].includes(value)) {
        this.form[field].push(value);
      } else {
        this.form[field] = this.form[field].filter(v => v !== value);
      }
    },

    flash(message) {
      this.toast = message;
      if (this.toastTimer) clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toast = ''; }, 3500);
    },
  };
}
