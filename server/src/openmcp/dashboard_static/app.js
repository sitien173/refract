document.addEventListener('alpine:init', () => {
  Alpine.data('dashboardApp', () => ({
    activeTab: 'overview',
    isConnected: true,
    lastUpdated: null,
    
    statusData: { status: 'loading', workers: 0, active_jobs: 0, queued_jobs: 0 },
    targets: [],
    profiles: { default: '', available: [] },
    projects: [],
    jobs: [],
    
    jobFilter: 'all',
    selectedJob: null,
    jobEvents: [],
    _jobRequestId: 0,

    configData: {
      daemon: { host: '127.0.0.1', port: 8765, max_jobs: 4, history_turns: 8, history_bytes: 65536, default_profile: 'balanced' },
      logging: { level: 'INFO', format: 'text', file: 'openmcp.log', console: false, max_bytes: 10485760, backup_count: 5, capture_warnings: true },
      targets: [],
      profiles: {}
    },
    configError: null,
    configSuccess: null,
    restartRequired: [],
    configLoading: false,

    taskGuideData: { recommendations: [] },
    taskGuideRawJson: '{}',
    taskGuideError: null,
    taskGuideSuccess: null,
    taskGuideLoading: false,
    
    mainTimer: null,

    jobTimer: null,
    isPaused: false,

    init() {
      this.refreshAll();
      this.fetchConfig();
      this.startPolling();
      
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
          this.pausePolling();
        } else {
          this.resumePolling();
        }
      });
    },

    startPolling() {
      if (this.mainTimer) clearInterval(this.mainTimer);
      this.mainTimer = setInterval(() => {
        if (!this.isPaused) {
          this.refreshAll();
        }
      }, 3000);
    },

    pausePolling() {
      this.isPaused = true;
      if (this.mainTimer) {
        clearInterval(this.mainTimer);
        this.mainTimer = null;
      }
      if (this.jobTimer) {
        clearInterval(this.jobTimer);
        this.jobTimer = null;
      }
    },

    resumePolling() {
      this.isPaused = false;
      this.refreshAll();
      this.startPolling();
      if (this.selectedJob) {
        this.startJobPolling();
      }
    },

    async refreshAll() {
      await Promise.all([
        this.fetchStatus(),
        this.fetchTargets(),
        this.fetchProfiles(),
        this.fetchProjects(),
        this.fetchJobs()
      ]);
      this.lastUpdated = new Date().toLocaleTimeString();
    },

    async fetchStatus() {
      try {
        const res = await fetch('/dashboard/api/status');
        if (res.ok) {
          this.statusData = await res.json();
          this.isConnected = true;
        } else {
          this.isConnected = false;
        }
      } catch (err) {
        this.isConnected = false;
      }
    },

    async fetchTargets() {
      try {
        const res = await fetch('/dashboard/api/targets');
        if (res.ok) {
          this.targets = await res.json();
        }
      } catch (err) {}
    },

    async fetchProfiles() {
      try {
        const res = await fetch('/dashboard/api/profiles');
        if (res.ok) {
          this.profiles = await res.json();
        }
      } catch (err) {}
    },

    async fetchProjects() {
      try {
        const res = await fetch('/dashboard/api/projects');
        if (res.ok) {
          this.projects = await res.json();
        }
      } catch (err) {}
    },

    async fetchJobs() {
      try {
        const projectsRes = await fetch('/dashboard/api/projects');
        if (!projectsRes.ok) return;
        const projectList = await projectsRes.json();
        
        let allJobs = [];
        for (const proj of projectList) {
          const res = await fetch(`/dashboard/api/projects/${proj.id}/jobs`);
          if (res.ok) {
            const list = await res.json();
            allJobs = allJobs.concat(list);
          }
        }
        allJobs.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
        this.jobs = allJobs;
      } catch (err) {}
    },

    get filteredJobs() {
      if (this.jobFilter === 'all') return this.jobs;
      return this.jobs.filter(j => j.state === this.jobFilter);
    },

    async openJobDetail(job) {
      this.selectedJob = job;
      await this.refreshJobDetail();
      this.startJobPolling();
    },

    closeJobDetail() {
      this.selectedJob = null;
      this.jobEvents = [];
      this._jobRequestId++;
      if (this.jobTimer) {
        clearInterval(this.jobTimer);
        this.jobTimer = null;
      }
    },

    startJobPolling() {
      if (this.jobTimer) clearInterval(this.jobTimer);
      this.jobTimer = setInterval(() => {
        if (!this.isPaused && this.selectedJob) {
          this.refreshJobDetail();
        }
      }, 2000);
    },

    async refreshJobDetail() {
      if (!this.selectedJob) return;
      const reqId = ++this._jobRequestId;
      const jobId = this.selectedJob.id;
      try {
        const jobRes = await fetch(`/dashboard/api/jobs/${jobId}`);
        const jobData = jobRes.ok ? await jobRes.json() : null;
        if (reqId !== this._jobRequestId) return;
        if (jobData) this.selectedJob = jobData;

        const eventsRes = await fetch(`/dashboard/api/jobs/${jobId}/events`);
        const eventsData = eventsRes.ok ? await eventsRes.json() : null;
        if (reqId !== this._jobRequestId) return;
        if (eventsData) this.jobEvents = eventsData;
      } catch (err) {}
    },

    formatTime(ts) {
      if (!ts) return '-';
      try {
        return new Date(ts).toLocaleString();
      } catch (e) {
        return ts;
      }
    },

    async fetchConfig() {
      this.configLoading = true;
      this.configError = null;
      try {
        const res = await fetch('/dashboard/api/config');
        if (res.ok) {
          this.configData = await res.json();
        } else {
          const data = await res.json();
          this.configError = data.error || 'Failed to load config';
        }
      } catch (err) {
        this.configError = 'Network error loading config';
      } finally {
        this.configLoading = false;
      }
    },

    addTarget() {
      if (!this.configData.targets) this.configData.targets = [];
      this.configData.targets.push({
        id: 'target-' + (this.configData.targets.length + 1),
        backend: 'codex',
        model: '',
        backend_profile: '',
        reasoning: '',
        system_prompt: '',
        isolated: false,
        read_only: false,
        max_concurrency: 1,
        capabilities: ['code', 'reasoning', 'review', 'consult'],
        args: []
      });
    },

    removeTarget(index) {
      this.configData.targets.splice(index, 1);
    },

    addProfile() {
      const name = prompt('Enter new profile name:');
      if (!name || !name.trim()) return;
      const key = name.trim();
      if (!this.configData.profiles) this.configData.profiles = {};
      if (this.configData.profiles[key]) return;
      this.configData.profiles[key] = {
        implement: { targets: [], max_attempts: 1, timeout_s: 0 },
        review: { targets: [], max_attempts: 1, timeout_s: 0 },
        consult: { targets: [], max_attempts: 1, timeout_s: 0 }
      };
    },

    removeProfile(key) {
      if (this.configData.profiles) {
        delete this.configData.profiles[key];
      }
    },

    validateClientConfig() {
      if (!this.configData.daemon) return 'Daemon configuration missing';
      const port = parseInt(this.configData.daemon.port, 10);
      if (isNaN(port) || port <= 0) return 'Daemon port must be a positive integer';
      const maxJobs = parseInt(this.configData.daemon.max_jobs, 10);
      if (isNaN(maxJobs) || maxJobs <= 0) return 'Daemon max_jobs must be a positive integer';

      if (!Array.isArray(this.configData.targets) || this.configData.targets.length === 0) {
        return 'At least one target must be configured';
      }

      const targetIds = new Set();
      for (const t of this.configData.targets) {
        if (!t.id || !t.id.trim()) return 'Target ID cannot be empty';
        if (targetIds.has(t.id.trim())) return `Duplicate target ID: ${t.id}`;
        targetIds.add(t.id.trim());
        if (!['codex', 'agy', 'pi'].includes(t.backend)) {
          return `Target ${t.id} has invalid backend: ${t.backend}`;
        }
      }

      if (!this.configData.profiles || Object.keys(this.configData.profiles).length === 0) {
        return 'At least one profile must be configured';
      }
      const defaultProf = (this.configData.daemon.default_profile || '').trim();
      if (defaultProf && !this.configData.profiles[defaultProf]) {
        return `Default profile '${defaultProf}' is not in configured profiles`;
      }

      return null;
    },

    async saveConfig() {
      this.configError = null;
      this.configSuccess = null;

      const clientErr = this.validateClientConfig();
      if (clientErr) {
        this.configError = clientErr;
        return;
      }

      const payload = JSON.parse(JSON.stringify(this.configData));
      payload.daemon.port = parseInt(payload.daemon.port, 10);
      payload.daemon.max_jobs = parseInt(payload.daemon.max_jobs, 10);
      payload.daemon.history_turns = parseInt(payload.daemon.history_turns, 10);
      payload.daemon.history_bytes = parseInt(payload.daemon.history_bytes, 10);

      for (const t of payload.targets) {
        t.max_concurrency = parseInt(t.max_concurrency, 10) || 1;
        if (typeof t.args === 'string') {
          t.args = t.args.split(',').map(s => s.trim()).filter(Boolean);
        }
      }

      try {
        const res = await fetch('/dashboard/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.success) {
          this.configSuccess = 'Configuration saved successfully.';
          this.restartRequired = data.restart_required || [];
          await this.fetchConfig();
          await this.fetchStatus();
        } else {
          this.configError = data.error || 'Failed to save configuration';
        }
      } catch (err) {
        this.configError = 'Network error saving configuration';
      }
    },

    async fetchTaskGuide() {
      this.taskGuideLoading = true;
      this.taskGuideError = null;
      try {
        const res = await fetch('/dashboard/api/task-guide');
        if (res.ok) {
          const guide = await res.json();
          this.taskGuideData = guide && typeof guide === 'object' ? guide : {};
          if (!Array.isArray(this.taskGuideData.recommendations)) {
            this.taskGuideData.recommendations = [];
          }
          this.taskGuideRawJson = JSON.stringify(this.taskGuideData, null, 2);
        } else {
          const data = await res.json();
          this.taskGuideError = data.error || 'Failed to load task guide';
        }
      } catch (err) {
        this.taskGuideError = 'Network error loading task guide';
      } finally {
        this.taskGuideLoading = false;
      }
    },

    syncGuideToRawJson() {
      this.taskGuideRawJson = JSON.stringify(this.taskGuideData, null, 2);
    },

    trySyncRawJsonToGuide() {
      try {
        const parsed = JSON.parse(this.taskGuideRawJson);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          this.taskGuideData = parsed;
          if (!Array.isArray(this.taskGuideData.recommendations)) {
            this.taskGuideData.recommendations = [];
          }
        }
      } catch (e) {}
    },

    addRecommendation() {
      if (!Array.isArray(this.taskGuideData.recommendations)) {
        this.taskGuideData.recommendations = [];
      }
      this.taskGuideData.recommendations.push({ task: '', profile: '' });
      this.syncGuideToRawJson();
    },

    removeRecommendation(index) {
      if (Array.isArray(this.taskGuideData.recommendations)) {
        this.taskGuideData.recommendations.splice(index, 1);
        this.syncGuideToRawJson();
      }
    },

    validateClientTaskGuide() {
      let parsed;
      try {
        parsed = JSON.parse(this.taskGuideRawJson);
      } catch (err) {
        return 'Invalid JSON syntax';
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || Object.keys(parsed).length === 0) {
        return 'Task guide must be a non-empty JSON object';
      }
      return null;
    },

    async saveTaskGuide() {
      this.taskGuideError = null;
      this.taskGuideSuccess = null;

      const clientErr = this.validateClientTaskGuide();
      if (clientErr) {
        this.taskGuideError = clientErr;
        return;
      }

      const payload = JSON.parse(this.taskGuideRawJson);

      try {
        const res = await fetch('/dashboard/api/task-guide', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          this.taskGuideSuccess = 'Task guide saved successfully.';
          this.taskGuideData = data;
          if (!Array.isArray(this.taskGuideData.recommendations)) {
            this.taskGuideData.recommendations = [];
          }
          this.taskGuideRawJson = JSON.stringify(this.taskGuideData, null, 2);
        } else {
          this.taskGuideError = data.error || 'Failed to save task guide';
        }
      } catch (err) {
        this.taskGuideError = 'Network error saving task guide';
      }
    }
  }));
});

