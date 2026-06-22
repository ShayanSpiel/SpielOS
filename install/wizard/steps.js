/* SpielOS Wizard — Alpine.js component.
   Production: real progress at top, file path hints per field, live banner
   preview, real color pickers, auto-install adapters on finish.
*/

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
      brand_name: 'SpielOS',
      handle: '@your_handle',
      tagline: 'Build to public.',
      creator_self: 'I am a builder.',
      primary_bg: '#000000',
      primary_fg: '#ffffff',
      accent: '#ff6a00',
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

    async init() {
      try {
        const r = await fetch('/api/config');
        const cfg = await r.json();
        this.target = cfg.target || '';
        if (cfg.existing && cfg.existing.summary) {
          Object.assign(this.form, cfg.existing.summary);
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
        const r = await fetch('/api/finish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.form)
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
        // Pick the closer copy from the install result
        if (this.installResult.adapters_installed > 0) {
          this.installResult.closer_takeaway = 'Installed. The team is on your IDEs.';
          this.installResult.closer_echo = `Published ${this.installResult.adapters_generated} agent files, installed ${this.installResult.adapters_installed} to your live IDE.`;
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
        localStorage.setItem('spielos-wizard-draft', JSON.stringify(this.form));
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
