import { useEffect, useState } from 'react'
import {
  getConfiguration,
  getProfiles,
  getConfigurationProfiles,
  getConfigurationProfile,
  deleteConfigurationProfile,
  DashboardApiError,
} from '../api'
import Alert from '../components/Alert'
import ConfigurationHealthBanner from '../components/ConfigurationHealthBanner'
import DataGrid from '../components/DataGrid'
import Inspector, { InspectorRow } from '../components/Inspector'
import PageHeader from '../components/PageHeader'
import ProfileEditor from '../components/ProfileEditor'
import Modal from '../components/Modal'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

export default function Profiles() {
  const { data, error, isLoading, refresh } = useDashboardQuery(getProfiles)
  const { data: configurationHealth, refresh: refreshConfigurationHealth } = useDashboardQuery(getConfiguration, { pollInterval: 5000 })

  const [selectedProfile, setSelectedProfile] = useState(null)
  const [selectedProfileDetails, setSelectedProfileDetails] = useState(null)
  const [announcement, setAnnouncement] = useState('')
  const [editorState, setEditorState] = useState({
    isOpen: false,
    mode: 'create',
    profile: null,
    revision: '',
    availableTargets: [],
    availableProfiles: [],
  })
  const [deleteDialogState, setDeleteDialogState] = useState({
    isOpen: false,
    profileId: '',
    revision: '',
    references: null,
    error: null,
    isSubmitting: false,
    isConfirmed: false,
  })

  const defaultProfile = data?.default || 'default'
  const available = data?.available || []

  const rows = available.map((name) => ({
    id: name,
    name,
    isDefault: name === defaultProfile,
  }))

  const columns = [
    {
      key: 'name',
      header: 'Profile identifier',
      width: '240px',
      render: (row) => <strong>{row.name}</strong>,
    },
    {
      key: 'isDefault',
      header: 'Default fallback',
      width: '180px',
      render: (row) => (
        <span className={`profile-tag ${row.isDefault ? 'profile-tag-default' : ''}`}>
          {row.isDefault ? 'Global default' : 'Profile'}
        </span>
      ),
    },
    {
      key: 'scope',
      header: 'Scope',
      width: '200px',
      render: () => <span>Global catalog</span>,
    },
  ]

  // Update selected profile details when selected profile changes
  useEffect(() => {
    if (!selectedProfile?.name) {
      setSelectedProfileDetails(null)
      return
    }

    let isMounted = true
    getConfigurationProfile(selectedProfile.name)
      .then((payload) => {
        if (isMounted) {
          setSelectedProfileDetails(payload.profile || null)
        }
      })
      .catch(() => {
        if (isMounted) {
          setSelectedProfileDetails(null)
        }
      })

    return () => {
      isMounted = false
    }
  }, [selectedProfile?.name])

  async function handleOpenCreate() {
    try {
      const payload = await getConfigurationProfiles()
      const profs = (payload.profiles || []).map((p) => p.id || p.name).filter(Boolean)
      setEditorState({
        isOpen: true,
        mode: 'create',
        profile: null,
        revision: payload.revision || '',
        availableTargets: payload.available_targets || [],
        availableProfiles: profs.length > 0 ? profs : available,
      })
    } catch {
      setEditorState({
        isOpen: true,
        mode: 'create',
        profile: null,
        revision: '',
        availableTargets: [],
        availableProfiles: available,
      })
    }
  }

  async function handleOpenEdit(profileId) {
    try {
      const [profilePayload, allProfilesPayload] = await Promise.all([
        getConfigurationProfile(profileId),
        getConfigurationProfiles().catch(() => ({ profiles: [], available_targets: [] })),
      ])
      const profs = (allProfilesPayload.profiles || []).map((p) => p.id || p.name).filter(Boolean)
      setEditorState({
        isOpen: true,
        mode: 'edit',
        profile: profilePayload.profile || null,
        revision: profilePayload.revision || '',
        availableTargets: profilePayload.available_targets || allProfilesPayload.available_targets || [],
        availableProfiles: profs.length > 0 ? profs : available,
      })
    } catch (err) {
      setAnnouncement(`Failed to load profile details: ${err.message || 'error'}`)
    }
  }

  async function handleOpenDelete(profileId) {
    try {
      const payload = await getConfigurationProfiles()
      setDeleteDialogState({
        isOpen: true,
        profileId,
        revision: payload.revision || '',
        references: null,
        error: null,
        isSubmitting: false,
        isConfirmed: false,
      })
    } catch (err) {
      setAnnouncement(`Failed to prepare profile deletion: ${err.message || 'error'}`)
    }
  }

  async function handleConfirmDelete() {
    setDeleteDialogState((prev) => ({ ...prev, isSubmitting: true, error: null }))
    try {
      await deleteConfigurationProfile(deleteDialogState.profileId, deleteDialogState.revision)
      setAnnouncement(`Profile "${deleteDialogState.profileId}" deleted.`)
      const deletedId = deleteDialogState.profileId
      setDeleteDialogState({
        isOpen: false,
        profileId: '',
        revision: '',
        references: null,
        error: null,
        isSubmitting: false,
        isConfirmed: false,
      })
      if (selectedProfile?.name === deletedId) {
        setSelectedProfile(null)
      }
      refresh()
      refreshConfigurationHealth()
    } catch (err) {
      if ((err instanceof DashboardApiError || err?.status === 409) && err?.payload?.code === 'referenced') {
        setDeleteDialogState((prev) => ({
          ...prev,
          isSubmitting: false,
          references: err.payload?.references || [],
        }))
      } else {
        setDeleteDialogState((prev) => ({
          ...prev,
          isSubmitting: false,
          error: err.payload?.error || err.message || 'Failed to delete profile.',
        }))
      }
    }
  }

  function handleProfileSaved(result) {
    setEditorState((prev) => ({ ...prev, isOpen: false }))
    refresh()
    refreshConfigurationHealth()
    if (result.profile && selectedProfile?.name === result.profile.id) {
      setSelectedProfileDetails(result.profile)
    }
  }

  async function handleReloadRequired() {
    refresh()
    refreshConfigurationHealth()
    if (editorState.isOpen) {
      if (editorState.mode === 'edit' && editorState.profile?.id) {
        try {
          const payload = await getConfigurationProfile(editorState.profile.id)
          setEditorState((prev) => ({
            ...prev,
            revision: payload.revision || '',
            profile: payload.profile || prev.profile,
          }))
          return payload
        } catch {
          return null
        }
      } else {
        try {
          const payload = await getConfigurationProfiles()
          setEditorState((prev) => ({
            ...prev,
            revision: payload.revision || '',
          }))
          return payload
        } catch {
          return null
        }
      }
    }
    return null
  }

  const hasDeleteReferences = Array.isArray(deleteDialogState.references) && deleteDialogState.references.length > 0
  const deleteDialogTitle = hasDeleteReferences
    ? `Cannot delete profile: ${deleteDialogState.profileId}`
    : `Delete profile: ${deleteDialogState.profileId}`
  const deleteAriaLabel = hasDeleteReferences
    ? `Blocking references for profile ${deleteDialogState.profileId}`
    : deleteDialogTitle

  return (
    <div className="page">
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>

      <PageHeader
        title="Profiles"
        description="Global workflow profiles and routing policy."
        actions={
          <div className="header-actions-group">
            <button
              type="button"
              className="button button-primary button-sm"
              onClick={handleOpenCreate}
            >
              Create profile
            </button>
            <button
              type="button"
              className="button button-ghost button-sm"
              onClick={() => {
                refresh()
                refreshConfigurationHealth()
              }}
              disabled={isLoading}
            >
              {isLoading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        }
      />

      {error && !data && (
        <Alert tone="error" title="Unable to load profiles">
          {error.message || 'Failed to fetch global profiles.'}
        </Alert>
      )}
      <ConfigurationHealthBanner health={configurationHealth} />

      {error && data && (
        <Alert tone="warning" title="Showing previously loaded profiles">
          Background refresh failed. The profile table remains unchanged; retry when the daemon is available.
        </Alert>
      )}

      <div className="profiles-layout">
        <div className="profiles-table-area">
          <DataGrid
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            onRowClick={(row) => setSelectedProfile(row)}
            emptyMessage="No global profiles found in configuration."
            ariaLabel="Global profiles table"
            isLoading={isLoading}
          />
        </div>

        {selectedProfile && (
          <Inspector
            title={selectedProfile.name}
            description="Global workflow routing policy and failover targets."
            onClose={() => setSelectedProfile(null)}
            actions={
              <div className="inspector-actions-group">
                <button
                  type="button"
                  className="button button-secondary button-sm"
                  onClick={() => handleOpenEdit(selectedProfile.name)}
                >
                  Edit profile
                </button>
                <button
                  type="button"
                  className="button button-destructive-outline button-sm"
                  onClick={() => handleOpenDelete(selectedProfile.name)}
                >
                  Delete profile
                </button>
              </div>
            }
          >
            <InspectorRow label="Identifier" value={selectedProfile.name} />
            <InspectorRow
              label="Fallback status"
              value={selectedProfile.isDefault ? 'Global default' : 'Custom profile'}
            />
            <InspectorRow
              label="Inherits from"
              value={selectedProfileDetails?.extends || 'None (base profile)'}
            />

            {selectedProfileDetails && (
              <div style={{ marginTop: 'var(--space-md)' }}>
                <h4 style={{ fontSize: 'var(--type-text-xs-size)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-subdued)', marginBottom: 'var(--space-xs)' }}>
                  Workflows
                </h4>
                {['consult', 'implement', 'review', 'other'].map((wf) => {
                  const declared = selectedProfileDetails.declared?.[wf]
                  const inherited = selectedProfileDetails.inherited?.[wf]
                  const effective = selectedProfileDetails.effective?.[wf]
                  const source = selectedProfileDetails.sources?.[wf]
                  const targets = effective?.targets || declared?.targets || inherited?.targets || []

                  return (
                    <div key={wf} style={{ marginBottom: 'var(--space-xs)', fontSize: 'var(--type-text-xs-size)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong style={{ textTransform: 'capitalize' }}>{wf}</strong>
                        <span className={`source-chip ${declared ? 'source-chip-declared' : 'source-chip-inherited'}`}>
                          {declared ? 'Declared' : (source ? `Inherited (${source})` : 'Undeclared')}
                        </span>
                      </div>
                      <div style={{ color: 'var(--color-text-subdued)', marginTop: '2px' }}>
                        Targets: <code>{targets.join(', ') || 'None'}</code>
                        {effective && ` (attempts: ${effective.max_attempts ?? 1}, timeout: ${effective.timeout_s ? `${effective.timeout_s}s` : 'none'})`}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Inspector>
        )}
      </div>

      <ProfileEditor
        isOpen={editorState.isOpen}
        mode={editorState.mode}
        profile={editorState.profile}
        revision={editorState.revision}
        availableTargets={editorState.availableTargets}
        availableProfiles={editorState.availableProfiles}
        onClose={() => setEditorState((prev) => ({ ...prev, isOpen: false }))}
        onSaved={handleProfileSaved}
        onAnnounce={(msg) => setAnnouncement(msg)}
        onReloadRequired={handleReloadRequired}
      />

      <Modal
        isOpen={deleteDialogState.isOpen}
        onClose={() => setDeleteDialogState((prev) => ({ ...prev, isOpen: false }))}
        title={deleteDialogTitle}
        role="dialog"
        ariaLabel={deleteAriaLabel}
      >
        {hasDeleteReferences ? (
          <div className="mutation-dialog-referenced">
            <Alert tone="warning" title="Profile is currently referenced">
              Profile <strong>{deleteDialogState.profileId}</strong> cannot be deleted because it is referenced by:
            </Alert>

            <div className="mutation-references-list" style={{ marginTop: 'var(--space-md)' }}>
              <table className="data-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Scope</th>
                    <th>Reference</th>
                    <th>Relationship</th>
                  </tr>
                </thead>
                <tbody>
                  {deleteDialogState.references.map((ref, idx) => (
                    <tr key={idx}>
                      <td>
                        <span className={`source-chip ${ref.scope === 'project' ? 'source-repository' : 'source-global'}`}>
                          {ref.scope === 'project' ? (ref.project_id ? `Project (${ref.project_id})` : 'Project') : 'Global'}
                        </span>
                      </td>
                      <td>
                        <strong>{ref.profile_id || '(daemon configuration)'}</strong>
                      </td>
                      <td>
                        <code>
                          {ref.relationship === 'default_profile'
                            ? 'Default profile'
                            : ref.relationship === 'extends'
                              ? 'Parent profile (extends)'
                              : ref.relationship || 'reference'}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="caption" style={{ marginTop: 'var(--space-md)' }}>
              Update or remove these references in configuration before deleting this profile.
            </p>

            <div className="modal-actions" style={{ justifyContent: 'flex-end', marginTop: 'var(--space-lg)' }}>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setDeleteDialogState((prev) => ({ ...prev, isOpen: false }))}
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (deleteDialogState.isConfirmed && !deleteDialogState.isSubmitting) {
                handleConfirmDelete()
              }
            }}
            className="mutation-dialog-confirm"
          >
            {deleteDialogState.error && (
              <div style={{ marginBottom: 'var(--space-md)' }}>
                <Alert tone="error" title="Action failed">
                  {deleteDialogState.error}
                </Alert>
              </div>
            )}

            <p style={{ margin: '0 0 var(--space-md) 0' }}>
              Are you sure you want to delete profile <strong>{deleteDialogState.profileId}</strong>? This action modifies the active configuration file.
            </p>

            <div className="confirmation-group" style={{ marginBottom: 'var(--space-md)' }}>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={deleteDialogState.isConfirmed}
                  onChange={(e) => setDeleteDialogState((prev) => ({ ...prev, isConfirmed: e.target.checked }))}
                  disabled={deleteDialogState.isSubmitting}
                  aria-label={`I confirm deleting profile ${deleteDialogState.profileId}`}
                />
                <span>I confirm deleting profile <strong>{deleteDialogState.profileId}</strong>.</span>
              </label>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setDeleteDialogState((prev) => ({ ...prev, isOpen: false }))}
                disabled={deleteDialogState.isSubmitting}
              >
                Cancel
              </button>
              <div className="modal-actions-right">
                <button
                  type="submit"
                  className="button button-destructive-outline"
                  disabled={!deleteDialogState.isConfirmed || deleteDialogState.isSubmitting}
                >
                  {deleteDialogState.isSubmitting ? 'Deleting…' : 'Confirm delete'}
                </button>
              </div>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
