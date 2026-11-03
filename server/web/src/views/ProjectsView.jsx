import React from 'react'
import { useProjects, useProject } from '../hooks/usePolling.js'

export function ProjectsView({ projectId = null }) {
  if (projectId) {
    return <ProjectDetailView projectId={projectId} />
  }
  return <ProjectListView />
}

function ProjectListView() {
  const { data: projects, isLoading, error } = useProjects()

  if (isLoading && !projects) {
    return (
      <main
        role="main"
        data-testid="projects-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          color: 'var(--text-description)',
          backgroundColor: 'var(--surface-neutral-01)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-sm)' }}>
          <div className="tds-spinner tds-spinner--sm" aria-hidden="true" />
          <span>Loading projects...</span>
        </div>
      </main>
    )
  }

  if (error && !projects) {
    return (
      <main
        role="main"
        data-testid="projects-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <div role="alert" className="tds-announcement tds-announcement--negative">
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">Failed to load projects</p>
            <p className="tds-announcement__message">{error.message || 'Network error'}</p>
          </div>
        </div>
      </main>
    )
  }

  const list = Array.isArray(projects) ? projects : []

  if (list.length === 0) {
    return (
      <main
        role="main"
        data-testid="projects-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          color: 'var(--text-description)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <p>No projects found.</p>
      </main>
    )
  }

  return (
    <main
      role="main"
      data-testid="projects-view"
      style={{
        flex: 1,
        padding: 'var(--padding-xl)',
        backgroundColor: 'var(--surface-neutral-01)',
        overflowY: 'auto',
      }}
    >
      <div style={{ marginBottom: 'var(--gap-lg)' }}>
        <h2
          style={{
            fontSize: 'var(--font-size-xl)',
            fontWeight: 'var(--font-weight-bold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-xs) 0',
          }}
        >
          Projects
        </h2>
        <p
          style={{
            fontSize: 'var(--font-size-sm)',
            color: 'var(--text-description)',
            margin: 0,
          }}
        >
          Configured workspaces and project catalogs.
        </p>
      </div>

      <div className="tds-data-table-container" style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-card)' }}>
        <div className="tds-data-table__wrapper">
          <table className="tds-data-table tds-data-table--compact">
            <thead>
              <tr>
                <th>Alias</th>
                <th>Path / ID</th>
                <th>Job Count</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {list.map((proj) => {
                const jobCount =
                  proj.job_counts !== undefined && proj.job_counts !== null
                    ? String(proj.job_counts)
                    : '-'
                return (
                  <tr key={proj.id}>
                    <td className="tds-data-table__text-cell">
                      <a
                        href={`#/projects/${encodeURIComponent(proj.id)}`}
                        style={{
                          color: 'var(--text-link)',
                          fontWeight: 'var(--font-weight-medium)',
                          textDecoration: 'none',
                        }}
                      >
                        {proj.alias || proj.id}
                      </a>
                    </td>
                    <td className="tds-data-table__text-cell">
                      <div>{proj.root || '-'}</div>
                      <span className="tds-data-table__cell-subtext">{proj.id}</span>
                    </td>
                    <td className="tds-data-table__text-cell">{jobCount}</td>
                    <td className="tds-data-table__text-cell">
                      <span className="tds-data-table__cell-subtext">
                        {proj.created_at || '-'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}

function ProjectDetailView({ projectId }) {
  const { data, isLoading, error } = useProject(projectId)

  if (isLoading && !data) {
    return (
      <main
        role="main"
        data-testid="project-detail-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          color: 'var(--text-description)',
          backgroundColor: 'var(--surface-neutral-01)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-sm)' }}>
          <div className="tds-spinner tds-spinner--sm" aria-hidden="true" />
          <span>Loading project details...</span>
        </div>
      </main>
    )
  }

  const isNotFound =
    Boolean(error && (error.status === 404 || error.message?.includes('not found') || error.message?.includes('Unknown project')))

  if (isNotFound) {
    return (
      <main
        role="main"
        data-testid="project-detail-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <div style={{ marginBottom: 'var(--gap-md)' }}>
          <a
            href="#/projects"
            style={{
              color: 'var(--text-link)',
              textDecoration: 'none',
              fontSize: 'var(--font-size-sm)',
            }}
          >
            &larr; Back to projects
          </a>
        </div>
        <div role="alert" className="tds-announcement tds-announcement--warning">
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">Project not found</p>
            <p className="tds-announcement__message">
              The project <strong>{projectId}</strong> was not found.
            </p>
          </div>
        </div>
      </main>
    )
  }

  if (error && !data) {
    return (
      <main
        role="main"
        data-testid="project-detail-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <div style={{ marginBottom: 'var(--gap-md)' }}>
          <a
            href="#/projects"
            style={{
              color: 'var(--text-link)',
              textDecoration: 'none',
              fontSize: 'var(--font-size-sm)',
            }}
          >
            &larr; Back to projects
          </a>
        </div>
        <div role="alert" className="tds-announcement tds-announcement--negative">
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">Error loading project</p>
            <p className="tds-announcement__message">{error.message || 'Unknown error'}</p>
          </div>
        </div>
      </main>
    )
  }

  const project = data?.project || {}
  const configuration = data?.configuration || {}
  const profiles = Array.isArray(configuration.profiles) ? configuration.profiles : []

  return (
    <main
      role="main"
      data-testid="project-detail-view"
      style={{
        flex: 1,
        padding: 'var(--padding-xl)',
        backgroundColor: 'var(--surface-neutral-01)',
        overflowY: 'auto',
      }}
    >
      <div style={{ marginBottom: 'var(--gap-md)' }}>
        <a
          href="#/projects"
          style={{
            color: 'var(--text-link)',
            textDecoration: 'none',
            fontSize: 'var(--font-size-sm)',
          }}
        >
          &larr; Back to projects
        </a>
      </div>

      <div style={{ marginBottom: 'var(--gap-xl)' }}>
        <h2
          style={{
            fontSize: 'var(--font-size-xl)',
            fontWeight: 'var(--font-weight-bold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-xs) 0',
          }}
        >
          {project.alias || project.id}
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap-md)', fontSize: 'var(--font-size-sm)', color: 'var(--text-description)' }}>
          <div>
            <strong>ID:</strong> {project.id}
          </div>
          <div>
            <strong>Root:</strong> {project.root || '-'}
          </div>
          <div>
            <strong>Created:</strong> {project.created_at || '-'}
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 'var(--gap-md)',
          marginBottom: 'var(--gap-xl)',
        }}
      >
        <div
          style={{
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-card)',
            padding: 'var(--padding-lg)',
            backgroundColor: 'var(--surface-neutral-02)',
          }}
        >
          <span style={{ fontSize: 'var(--font-size-xs)', textTransform: 'uppercase', color: 'var(--text-caption)' }}>
            Global Default Profile
          </span>
          <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--text-default)', marginTop: 'var(--gap-xs)' }}>
            {configuration.global_default_profile || '-'}
          </div>
        </div>

        <div
          style={{
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-card)',
            padding: 'var(--padding-lg)',
            backgroundColor: 'var(--surface-neutral-02)',
          }}
        >
          <span style={{ fontSize: 'var(--font-size-xs)', textTransform: 'uppercase', color: 'var(--text-caption)' }}>
            Project Default Profile
          </span>
          <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--text-default)', marginTop: 'var(--gap-xs)' }}>
            {configuration.project_default_profile || '-'}
          </div>
        </div>
      </div>

      <div>
        <h3
          style={{
            fontSize: 'var(--font-size-lg)',
            fontWeight: 'var(--font-weight-semibold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-md) 0',
          }}
        >
          Profiles and Workflows
        </h3>

        {profiles.length === 0 ? (
          <p style={{ color: 'var(--text-description)', fontSize: 'var(--font-size-sm)' }}>
            No profiles defined.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap-lg)' }}>
            {profiles.map((prof) => {
              const effective = prof.effective || {}
              const workflows = Object.keys(effective)
              const sources = prof.sources || {}

              return (
                <div
                  key={prof.id}
                  style={{
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-card)',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      padding: 'var(--padding-md) var(--padding-lg)',
                      backgroundColor: 'var(--surface-neutral-02)',
                      borderBottom: '1px solid var(--border-subtle)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 'var(--font-weight-semibold)', color: 'var(--text-default)' }}>
                        {prof.id}
                      </span>
                      {prof.parent?.value && (
                        <span style={{ marginLeft: 'var(--gap-sm)', fontSize: 'var(--font-size-xs)', color: 'var(--text-description)' }}>
                          extends {prof.parent.value} ({prof.parent.source || 'global'})
                        </span>
                      )}
                    </div>
                  </div>

                  {workflows.length === 0 ? (
                    <div style={{ padding: 'var(--padding-md)', color: 'var(--text-description)', fontSize: 'var(--font-size-sm)' }}>
                      No workflows configured.
                    </div>
                  ) : (
                    <div className="tds-data-table-container">
                      <div className="tds-data-table__wrapper">
                        <table className="tds-data-table tds-data-table--compact">
                          <thead>
                            <tr>
                              <th>Workflow</th>
                              <th>Target Chain</th>
                              <th>Timeout</th>
                              <th>Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {workflows.map((wf) => {
                              const selection = effective[wf] || {}
                              const targets = selection.targets || []
                              const timeoutS = selection.timeout_s
                              const source = sources[wf] || 'global'
                              const isOverride = source === 'project'

                              return (
                                <tr key={wf}>
                                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                                    {wf}
                                  </td>
                                  <td className="tds-data-table__text-cell">
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap-xs)', alignItems: 'center' }}>
                                      {targets.length > 0 ? (
                                        targets.map((t, idx) => (
                                          <React.Fragment key={t}>
                                            <span className="tds-tag tds-tag--default">
                                              {t}
                                            </span>
                                            {idx < targets.length - 1 && (
                                              <span style={{ color: 'var(--text-caption)' }}>&rarr;</span>
                                            )}
                                          </React.Fragment>
                                        ))
                                      ) : (
                                        <span style={{ color: 'var(--text-disabled)' }}>none</span>
                                      )}
                                    </div>
                                  </td>
                                  <td className="tds-data-table__text-cell">
                                    {timeoutS ? `${timeoutS}s` : '-'}
                                  </td>
                                  <td className="tds-data-table__text-cell">
                                    <span
                                      className={`tds-tag ${
                                        isOverride ? 'tds-tag--intermediate' : 'tds-tag--default'
                                      }`}
                                    >
                                      {source}
                                    </span>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </main>
  )
}

export default ProjectsView
