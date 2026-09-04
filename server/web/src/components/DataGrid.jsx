import LoadingRows from './LoadingRows'

export default function DataGrid({
  columns = [],
  rows = [],
  rowKey,
  onRowClick,
  emptyMessage = 'No records found.',
  recoveryAction,
  ariaLabel = 'Data table',
  isLoading = false,
  loadingRowCount = 4,
}) {
  const isInteractive = typeof onRowClick === 'function'

  return (
    <div
      className="data-grid-container"
      tabIndex={0}
      role="region"
      aria-label={ariaLabel}
    >
      <table className="data-grid-table">
        <colgroup>
          {columns.map((col) => (
            <col key={col.key} style={col.width ? { width: col.width } : undefined} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                style={col.width ? { width: col.width } : undefined}
                className={col.align ? `text-${col.align}` : undefined}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading && (!rows || rows.length === 0) ? (
            <LoadingRows columns={columns} count={loadingRowCount} />
          ) : rows && rows.length > 0 ? (
            rows.map((row, index) => {
              const key = rowKey ? rowKey(row, index) : row.id || index
              return (
                <tr
                  key={key}
                  className={`data-grid-row ${isInteractive ? 'data-grid-row-interactive' : ''}`}
                  tabIndex={isInteractive ? 0 : undefined}
                  onClick={
                    isInteractive
                      ? (e) => {
                          if (e.defaultPrevented) return
                          if (e.button !== 0) return
                          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
                          if (e.target.closest('a, button, input, select, textarea')) return
                          onRowClick(row, e)
                        }
                      : undefined
                  }
                  onKeyDown={
                    isInteractive
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            if (e.target.closest('a, button, input, select, textarea')) return
                            e.preventDefault()
                            onRowClick(row, e)
                          }
                        }
                      : undefined
                  }
                >
                  {columns.map((col) => {
                    const rawValue = col.render ? col.render(row, index) : row[col.key]
                    const titleText =
                      typeof rawValue === 'string' || typeof rawValue === 'number'
                        ? String(rawValue)
                        : typeof row[col.key] === 'string' || typeof row[col.key] === 'number'
                          ? String(row[col.key])
                          : undefined
                    return (
                      <td
                        key={col.key}
                        className={`data-grid-cell ${col.align ? `text-${col.align}` : ''}`}
                        title={titleText}
                      >
                        {rawValue}
                      </td>
                    )
                  })}
                </tr>
              )
            })
          ) : (
            <tr className="data-grid-empty-row">
              <td colSpan={columns.length} className="data-grid-empty-cell">
                <div className="empty-state">
                  <p className="empty-message">{emptyMessage}</p>
                  {recoveryAction && <div className="recovery-action">{recoveryAction}</div>}
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
