/* SpielOS Wizard — Alpine.js component.
   Loaded by index.html. Provides the wizard() component.
*/

function wizard() {
  return {
    current: 0,
    saving: false,
    done: false,
    target: '',
    doneLines: [],
    bufferLoading: false,
    bufferChannels: [],
    bufferError: '',

    form: {
      // Step 1: Brand
      brand_name: 'SpielOS',
      handle: '@your_handle',
      tagline: 'Build to public.',
      creator_self: 'I am a builder.',
      primary_bg: '#000000',
      primary_fg: '#ffffff',
      accent: '#ff6a00',
      // Step 2: Identity
      role: '',
      story: '',
      methodology_sources: ['Build sessions'],
      // Step 3: ICP
      icp_who: '',
      icp_age: '',
      icp_revenue: '',
      icp_goal: '',
      icp_fear: '',
      icp_questions: '',
      // Step 4: Positioning
      positioning: '',
      category: '',
      core_insight: '',
      // Step 5: Offer
      offer_name: '',
      offer_price: '',
      offer_stack: '',
      offer_guarantee: '',
      // Step 6: Funnel
      funnel_tofu: 40,
      funnel_mofu: 40,
      funnel_bofu: 15,
      archetypes: ['System Build', 'Ship', 'Decision', 'Lesson'],
      // Step 7: Voice
      voice_register: 'confessional-teaching',
      voice_rules: [
        'No em-dashes (use →, colons, commas)',
        'Standard capitalization',
        'Note: closer preferred'
      ],
      banned_openers: '^in this post\n^today i want to talk about\n^hey friends\n^excited to share',
      // Step 8: Methodology
      methodology_name: 'Session as Content',
      methodology_desc: '',
      platforms: ['x', 'linkedin'],
      // Step 9: Connect
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
      { key: 'welcome',     label: 'Welcome',     sub: '5 min, 10 steps' },
      { key: 'brand',       label: 'Brand',       sub: 'Visual identity' },
      { key: 'identity',    label: 'Identity',    sub: 'Who you are' },
      { key: 'icp',         label: 'ICP',         sub: 'Who you serve' },
      { key: 'positioning', label: 'Positioning', sub: 'Your one-liner' },
      { key: 'offer',       label: 'Offer',       sub: 'What you sell' },
      { key: 'funnel',      label: 'Funnel',      sub: 'How readers move' },
      { key: 'voice',       label: 'Voice',       sub: 'How posts read' },
      { key: 'methodology', label: 'Methodology', sub: 'Where content comes from' },
      { key: 'connect',     label: 'Connect',     sub: 'API tokens' },
      { key: 'done',        label: 'Done',        sub: 'Filed.' },
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

    async next() {
      if (this.current < 9) {
        this.current += 1;
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      // Step 9 → finish
      await this.finish();
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
          alert('Setup failed: ' + (data.error || 'unknown error'));
          this.saving = false;
          return;
        }
        this.doneLines = data.written || [];
        this.done = true;
        this.current = 10;
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        alert('Setup failed: ' + e);
      } finally {
        this.saving = false;
      }
    },

    saveAndQuit() {
      // Persist current state to localStorage so re-opening picks up
      try {
        localStorage.setItem('spielos-wizard-draft', JSON.stringify(this.form));
        alert('Saved! Re-run `spiel init` to pick up where you left off.');
        window.close();
      } catch (e) {
        alert('Could not save draft: ' + e);
      }
    },

    closeTab() {
      window.close();
      setTimeout(() => { window.location.href = 'about:blank'; }, 100);
    },
  };
}
