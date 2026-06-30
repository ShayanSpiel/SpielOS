/* ═══════════════════════════════════════════════════════
   SpielOS Wizard — Alpine.js component
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
  'trending-up':    '<path d="M23 6l-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/>',
  'crosshair':      '<circle cx="12" cy="12" r="10"/><path d="M12 2v4"/><path d="M12 18v4"/><path d="M2 12h4"/><path d="M18 12h4"/>',
  'bulb':           '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 00-4 12.7V17h8v-2.3A7 7 0 0012 2z"/>',
  'ban':            '<circle cx="12" cy="12" r="10"/><path d="M4.93 4.93l14.14 14.14"/>',
  'layers':         '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
  'award':          '<circle cx="12" cy="8" r="7"/><path d="M8.21 13.89L7 23l5-3 5 3-1.21-9.12"/>',
  'feather':        '<path d="M20.24 12.24a6 6 0 00-8.49-8.49L5 10.5V19h8.5z"/><path d="M16 8L2 22"/><path d="M17.5 15H9"/>',
  'git-pull-request': '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9V6a3 3 0 00-3-3H6"/><path d="M6 15V9"/>',
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

function wizard() {
  return {
    current: 0,
    saving: false,
    done: false,
    toast: '',
    toastTimer: null,
    target: '',
    doneLines: [],
    installResult: null,
    bufferLoading: false,
    bufferError: '',
    bufferChannels: [],

    expanded: {
      banner: false,
      preview: false,
      buffer: false,
      x: false,
      linkedin: false,
      blog: false,
    },

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

    colorFields: [
      { key: 'primary_bg', label: 'Background' },
      { key: 'primary_fg', label: 'Title' },
      { key: 'subtitle_color', label: 'Subtitle' },
      { key: 'handle_color', label: 'Handle' },
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
      voice_preset: 'direct',
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
      blog_repo: '',
      blog_token: '',
    },

    get iconKey() { return pickIcon(this.form.brand_name, this.form.tagline); },
    get iconSvg() {
      const key = this.iconKey;
      return window.icon(key) || window.icon('arrow-up-right');
    },

    async init() {
      await this.loadTarget();
      await this.loadSkeletons();
    },

    icon(name) { return window.icon(name); },

    async loadTarget() {
      try {
        const r = await fetch('/api/config');
        const data = await r.json();
        this.target = data.target || '';
      } catch {}
    },

    next() {
      if (this.current === this.steps.length - 2) {
        this.finish();
        return;
      }
      if (this.current < this.steps.length - 2) {
        this.current++;
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
    },

    back() {
      if (this.current > 0) {
        this.current--;
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },

    go(i) {
      this.current = i;
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },

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
      } catch { return ''; }
    },

    async fetchBufferChannels() {
      if (!this.form.buffer_token) { this.bufferError = 'Paste your Buffer access token first.'; return; }
      this.bufferLoading = true; this.bufferError = ''; this.bufferChannels = [];
      try {
        const r = await fetch('/api/buffer/channels', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: this.form.buffer_token }),
        });
        const data = await r.json();
        if (!data.ok) { this.bufferError = data.error || 'Buffer rejected the token.'; this.flash(this.bufferError); return; }
        this.bufferChannels = data.channels || [];
        this.flash(`Loaded ${this.bufferChannels.length} channels from Buffer.`);
      } catch (e) {
        this.bufferError = 'Could not reach Buffer. Check your network and try again.';
        this.flash(this.bufferError);
      } finally { this.bufferLoading = false; }
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
        if (!data.ok) { this.flash(data.error || 'Install failed'); this.saving = false; return; }
        this.done = true;
        this.doneLines = (data.written || []).map(f => `${f}  written`);
        this.installResult = data.install || {};
        if (data.install && data.install.errors && data.install.errors.length) {
          this.doneLines.push(`warnings: ${data.install.errors.join(', ')}`);
        }
        this.current = this.steps.length - 1;
        this.flash('Installed. Vault is live.');
        setTimeout(() => { window.location.href = '/dashboard'; }, 2000);
      } catch (e) {
        this.flash('Install failed: ' + e.message);
      }
      this.saving = false;
    },

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
