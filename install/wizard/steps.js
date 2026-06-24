/* SpielOS Wizard — Alpine.js component (lean 6-step).
   Welcome → Brand → Audience → Offer → Voice → Examples → Connect
*/

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
  'arrow-up-right': '<path d="M7 17 L17 7 M7 7 H17 V17" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'sparkles':      '<path d="M12 3 L13.5 8.5 L19 10 L13.5 11.5 L12 17 L10.5 11.5 L5 10 L10.5 8.5 Z M18 3 L18.5 5 L20.5 5.5 L18.5 6 L18 8 L17.5 6 L15.5 5.5 L17.5 5 Z M5 16 L5.5 18 L7.5 18.5 L5.5 19 L5 21 L4.5 19 L2.5 18.5 L4.5 18 Z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'trending-up':   '<path d="M3 17 L9 11 L13 15 L21 7 M15 7 L21 7 L21 13" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'crosshair':     '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2" fill="none"/><line x1="12" y1="2" x2="12" y2="6" stroke="currentColor" stroke-width="2"/><line x1="12" y1="18" x2="12" y2="22" stroke="currentColor" stroke-width="2"/><line x1="2" y1="12" x2="6" y2="12" stroke="currentColor" stroke-width="2"/><line x1="18" y1="12" x2="22" y2="12" stroke="currentColor" stroke-width="2"/>',
  'bulb':          '<path d="M9 18 H15 M10 22 H14 M12 2 A7 7 0 0 1 17 14 L17 16 H7 L7 14 A7 7 0 0 1 12 2 Z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'ban':           '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none"/><line x1="5" y1="5" x2="19" y2="19" stroke="currentColor" stroke-width="2"/>',
  'layers':        '<polygon points="12,2 22,8 12,14 2,8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polyline points="2,12 12,18 22,12" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polyline points="2,16 12,22 22,16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'award':         '<circle cx="12" cy="9" r="6" stroke="currentColor" stroke-width="2" fill="none"/><path d="M9 14 L7 22 L12 19 L17 22 L15 14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'feather':       '<path d="M20 4 C20 4 14 4 10 8 C6 12 4 18 4 18 L8 16 C8 16 6 22 6 22 L8 20 C8 20 14 20 18 16 C22 12 20 4 20 4 Z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="4" y1="20" x2="10" y2="14" stroke="currentColor" stroke-width="1.5"/>',
  'cog':           '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2" fill="none"/><path d="M12 2 V5 M12 19 V22 M2 12 H5 M19 12 H22 M5 5 L7 7 M17 17 L19 19 M5 19 L7 17 M17 7 L19 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  'git-pull-request': '<circle cx="6" cy="6" r="2.5" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="18" cy="18" r="2.5" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="18" cy="6" r="2.5" stroke="currentColor" stroke-width="2" fill="none"/><line x1="6" y1="9" x2="6" y2="20" stroke="currentColor" stroke-width="2"/><line x1="18" y1="9" x2="18" y2="15" stroke="currentColor" stroke-width="2"/><line x1="6" y1="20" x2="18" y2="20" stroke="currentColor" stroke-width="2"/>',
};

function pickIcon(brandName, tagline, icp) {
  const text = `${brandName || ''} ${tagline || ''} ${icp || ''}`.toLowerCase();
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
    target: '',
    doneLines: [],
    installResult: null,
    toast: '',
    toastTimer: null,
    bufferLoading: false,
    bufferChannels: [],
    bufferError: '',

    form: {
      brand_name: 'YourBrand',
      handle: '@your_handle',
      tagline: '',
      creator_self: '',
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
      blog_repo: '',
      blog_token: '',
    },

    steps: [
      { key: 'welcome',   label: 'Welcome' },
      { key: 'brand',     label: 'Brand' },
      { key: 'audience',  label: 'Audience' },
      { key: 'offer',     label: 'Offer' },
      { key: 'voice',     label: 'Voice' },
      { key: 'examples',  label: 'Examples' },
      { key: 'connect',   label: 'Connect' },
      { key: 'done',      label: 'Done' },
    ],

    get iconKey() {
      return pickIcon(this.form.brand_name, this.form.tagline, this.form.audience_content);
    },

    get iconSvg() {
      const key = this.iconKey;
      const path = ICON_SVG[key] || ICON_SVG['arrow-up-right'];
      return `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${path}</svg>`;
    },

    async init() {
      try {
        const r = await fetch('/api/config');
        const cfg = await r.json();
        this.target = cfg.target || '';
        if (cfg.existing && cfg.existing.summary) {
          Object.assign(this.form, cfg.existing.summary);
        }
        await this.loadSkeletons();
      } catch (e) {
        console.error('init failed', e);
      }
    },

    async loadSkeletons() {
      try {
        const r = await fetch('/api/skeletons');
        const data = await r.json();
        const skeletons = data.skeletons || [];
        for (const name of skeletons) {
          const res = await fetch(`/api/skeleton/${name}`);
          const skel = await res.json();
          const content = skel.content || '';
          switch (name) {
            case 'audience.md': this.form.audience_content = content; break;
            case 'offer.md':    this.form.offer_content = content; break;
            case 'voice.md':    this.form.voice_content = content; break;
            case 'examples.md': this.form.examples_content = content; break;
          }
        }
      } catch (e) {
        console.error('skeleton load failed', e);
      }
    },

    showToast(message, duration = 4500) {
      this.toast = message;
      if (this.toastTimer) clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toast = ''; }, duration);
    },

    next() {
      if (this.current < 6) {
        this.current += 1;
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      this.finish();
    },

    back() {
      if (this.current > 0) {
        this.current -= 1;
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },

    go(i) {
      this.current = i;
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    toggle(field, value) {
      if (!this.form[field].includes(value)) {
        this.form[field].push(value);
      } else {
        this.form[field] = this.form[field].filter(v => v !== value);
      }
    },

    async fetchBufferChannels() {
      if (!this.form.buffer_token) return;
      this.bufferLoading = true;
      this.bufferError = '';
      try {
        const r = await fetch('/api/buffer-channels', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: this.form.buffer_token }),
        });
        const data = await r.json();
        if (data.error) {
          this.bufferError = data.error;
        } else {
          this.bufferChannels = data.channels || [];
        }
      } catch (e) {
        this.bufferError = 'Failed to fetch channels';
      }
      this.bufferLoading = false;
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
        if (data.ok) {
          this.done = true;
          this.current = 7;
          this.doneLines = (data.written || []).map(f => `${f}  written`);
          this.installResult = {
            closer_takeaway: 'You stay a builder. The team ships the post.',
            closer_echo: 'From any IDE, type /post. The 5 roles take it from there.',
          };
          if (data.install && data.install.errors && data.install.errors.length) {
            this.doneLines.push(`warnings: ${data.install.errors.join(', ')}`);
          }
        } else {
          this.showToast(data.error || 'Failed to save');
        }
      } catch (e) {
        this.showToast('Failed to save: ' + e.message);
      }
      this.saving = false;
    },

    async saveAndQuit() {
      this.showToast('Progress saved locally. Run `spiel init` to resume.');
    },

    closeTab() {
      window.close();
    },
  };
}
