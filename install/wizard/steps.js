/* SpielOS Wizard — Alpine.js component.
   Production polish: full 10-step stepper, sticky nav, custom archetypes,
   real icon watermark in the live banner preview, auto-install on finish.
*/

const DEFAULT_ARCHETYPES = [
  'System Build', 'Ship', 'Decision', 'Lesson', 'Failure',
  'Client Work', 'Research', 'Tooling', 'Strategy', 'Meta'
];

/* Icon mapping (mirrors system/brand.json). First matching pattern wins. */
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

/* SVG path library (24x24, currentColor) — matches the SVGs in assets/icons */
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
  'code':          '<polyline points="16,18 22,12 16,6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polyline points="8,6 2,12 8,18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="14" y1="4" x2="10" y2="20" stroke="currentColor" stroke-width="2"/>',
  'mail':          '<rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><polyline points="3,7 12,13 21,7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'terminal':      '<polyline points="4,6 8,10 4,14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="12" y1="14" x2="20" y2="14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><rect x="2" y="3" width="20" height="18" rx="2" stroke="currentColor" stroke-width="2" fill="none"/>',
  'qrcode':        '<rect x="3" y="3" width="7" height="7" stroke="currentColor" stroke-width="2" fill="none"/><rect x="14" y="3" width="7" height="7" stroke="currentColor" stroke-width="2" fill="none"/><rect x="3" y="14" width="7" height="7" stroke="currentColor" stroke-width="2" fill="none"/><line x1="14" y1="14" x2="17" y2="14" stroke="currentColor" stroke-width="2"/><line x1="21" y1="14" x2="21" y2="17" stroke="currentColor" stroke-width="2"/><line x1="14" y1="18" x2="14" y2="21" stroke="currentColor" stroke-width="2"/><line x1="18" y1="18" x2="21" y2="18" stroke="currentColor" stroke-width="2"/><line x1="18" y1="21" x2="21" y2="21" stroke="currentColor" stroke-width="2"/>',
  'location':      '<path d="M12 22 C12 22 5 14 5 9 A7 7 0 0 1 19 9 C19 14 12 22 12 22 Z" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="9" r="2.5" stroke="currentColor" stroke-width="2" fill="none"/>',
};

/* Pick the icon for the current brand context */
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
    newArchetype: '',
    customArchetypes: [],

    DEFAULT_ARCHETYPES,

    form: {
      brand_name: 'SpielOS',
      handle: '@your_handle',
      tagline: 'Build to public.',
      creator_self: 'I am a builder.',
      primary_bg: '#000000',
      primary_fg: '#ffffff',
      subtitle_color: '#8a8a8a',
      handle_color: '#505050',
      accent: '#ff6a00',
      title_gradient: false,
      role: '',
      story: '',
      methodology_sources: ['Build sessions'],
      icp_who: '',
      icp_age: '',
      icp_revenue: '',
      icp_goal: '',
      icp_fear: '',
      icp_questions: '',
      positioning: '',
      category: '',
      core_insight: '',
      offer_name: '',
      offer_price: '',
      offer_stack: '',
      offer_guarantee: '',
      funnel_tofu: 40,
      funnel_mofu: 40,
      funnel_bofu: 15,
      archetypes: ['System Build', 'Ship', 'Decision', 'Lesson'],
      voice_register: 'confessional-teaching',
      voice_rules: [
        'No em-dashes (use →, colons, commas)',
        'Standard capitalization',
        'Note: closer preferred'
      ],
      banned_openers: '^in this post\n^today i want to talk about\n^hey friends\n^excited to share',
      methodology_name: 'Session as Content',
      methodology_desc: '',
      platforms: ['x', 'linkedin'],
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
      { key: 'welcome',     label: 'Welcome' },
      { key: 'brand',       label: 'Brand' },
      { key: 'identity',    label: 'Identity' },
      { key: 'icp',         label: 'ICP' },
      { key: 'positioning', label: 'Positioning' },
      { key: 'offer',       label: 'Offer' },
      { key: 'funnel',      label: 'Funnel' },
      { key: 'voice',       label: 'Voice' },
      { key: 'methodology', label: 'Methodology' },
      { key: 'connect',     label: 'Connect' },
      { key: 'done',        label: 'Done' },
    ],

    get iconKey() {
      return pickIcon(this.form.brand_name, this.form.tagline, this.form.icp_who);
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
          if (Array.isArray(cfg.existing.summary.customArchetypes)) {
            this.customArchetypes = cfg.existing.summary.customArchetypes;
          }
        }
      } catch (e) {
        console.error('config fetch failed', e);
      }
    },

    showToast(message, duration = 4500) {
      this.toast = message;
      if (this.toastTimer) clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toast = ''; }, duration);
    },

    next() {
      if (this.current < 9) {
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

    addCustomArchetype() {
      const v = this.newArchetype.trim();
      if (!v) return;
      // Don't add if it's already in defaults or already added
      if (this.DEFAULT_ARCHETYPES.includes(v) || this.customArchetypes.includes(v)) {
        this.newArchetype = '';
        return;
      }
      this.customArchetypes.push(v);
      this.form.archetypes.push(v);
      this.newArchetype = '';
      this.showToast(`Added "${v}"`);
    },

    removeCustomArchetype(name) {
      this.customArchetypes = this.customArchetypes.filter(a => a !== name);
      this.form.archetypes = this.form.archetypes.filter(a => a !== name);
    },

    async fetchBufferChannels() {
      this.bufferError = '';
      this.bufferLoading = true;
      try {
        const r = await fetch('/api/buffer-channels', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: this.form.buffer_token })
        });
        const data = await r.json();
        if (!r.ok) {
          this.bufferError = data.error || 'Failed to fetch channels';
          this.bufferChannels = [];
        } else {
          this.bufferChannels = data.channels || [];
          this.showToast(`Found ${data.channels.length} channels`);
        }
      } catch (e) {
        this.bufferError = String(e);
      } finally {
        this.bufferLoading = false;
      }
    },

    async finish() {
      this.saving = true;
      try {
        // Include custom archetypes in the payload
        const payload = { ...this.form, customArchetypes: this.customArchetypes };
        const r = await fetch('/api/finish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await r.json();
        if (!r.ok) {
          this.showToast('Setup failed: ' + (data.error || 'unknown error'), 8000);
          this.saving = false;
          return;
        }
        this.doneLines = data.written || [];
        this.installResult = data.install || {};
        this.done = true;
        this.current = 10;
        if (this.installResult.adapters_installed > 0) {
          this.installResult.closer_takeaway = 'Installed. The team is on your IDEs.';
          this.installResult.closer_echo = `Generated ${this.installResult.adapters_generated} agent files, installed ${this.installResult.adapters_installed} to your live IDE.`;
        }
        this.showToast('✓ Setup complete', 6000);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        this.showToast('Setup failed: ' + e, 8000);
      } finally {
        this.saving = false;
      }
    },

    saveAndQuit() {
      try {
        localStorage.setItem('spielos-wizard-draft', JSON.stringify({
          form: this.form, customArchetypes: this.customArchetypes
        }));
        this.showToast('Draft saved. Re-run `spiel init` to resume.', 5000);
        setTimeout(() => { window.close(); }, 1500);
      } catch (e) {
        this.showToast('Could not save: ' + e, 5000);
      }
    },

    closeTab() {
      window.close();
      setTimeout(() => { window.location.href = 'about:blank'; }, 200);
    },
  };
}
