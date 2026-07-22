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
    
    mainTimer: null,
    jobTimer: null,
    isPaused: false,

    init() {
      this.refreshAll();
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
    }
  }));
});
