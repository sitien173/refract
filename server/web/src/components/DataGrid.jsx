import { useEffect, useMemo, useRef, useState } from 'react'
import LoadingRows from './LoadingRows'

function getInitialVisibility(cols, defaultVis) {
  const vis = {}
  for (const col of cols) {
    if (defaultVis && defaultVis[col.key] !== undefined) {
      vis[col.key] = !!defaultVis[col.key]
    } else if (typeof col.defaultVisible === 'boolean') {
      vis[col.key] = col.defaultVisible
    } else if (col.priority === 'optional') {
      vis[col.key] = false
    } else {
      vis[col.key] = true
    }
  }
  return vis
}

function compareValues(a, b) {
  const aEmpty = a === null || a === undefined || a === ''
  const bEmpty = b === null || b === undefined || b === ''
  if (aEmpty && bEmpty) return 0
  if (aEmpty) return 1
  if (bEmpty) return -1

  if (typeof a === 'number' && typeof b === 'number') {
    return a - b
  }

  const aNum = typeof a === 'string' && a.trim() !== '' ? Number(a) : NaN
  const bNum = typeof b === 'string' && b.trim() !== '' ? Number(b) : NaN
  if (!Number.isNaN(aNum) && !Number.isNaN(bNum) && typeof a !== 'boolean' && typeof b !== 'boolean') {
    return aNum - bNum
  }

  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
}

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
  // Sorting props
  sort,
  sortConfig,
  defaultSort,
  defaultSortConfig,
  onSortChange,
  // Visibility props
  columnVisibility,
  defaultColumnVisibility,
  onColumnVisibilityChange,
  // Toolbar / customization
  toolbar,
  showToolbar = true,
  enableColumnVisibility = true,
}) {
  const isInteractive = typeof onRowClick === 'function'

  // Controlled vs uncontrolled visibility
  const isVisibilityControlled = columnVisibility !== undefined
  const [internalVisibility, setInternalVisibility] = useState(() =>
    getInitialVisibility(columns, defaultColumnVisibility)
  )
  const activeVisibility = isVisibilityControlled ? columnVisibility : internalVisibility

  // Controlled vs uncontrolled sorting
  const isSortControlled = sort !== undefined || sortConfig !== undefined
  const resolvedDefaultSort = defaultSort !== undefined ? defaultSort : (defaultSortConfig || null)
  const [internalSort, setInternalSort] = useState(resolvedDefaultSort)
  const activeSort = isSortControlled ? (sort !== undefined ? sort : sortConfig) : internalSort

  // Columns menu open state
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!isMenuOpen) return
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setIsMenuOpen(false)
      }
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setIsMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isMenuOpen])

  // Primary columns tracking
  const primaryKeys = useMemo(() => {
    return columns
      .filter((col) => (col.priority || 'primary') === 'primary')
      .map((col) => col.key)
  }, [columns])

  const visiblePrimaryCount = useMemo(() => {
    return primaryKeys.filter((key) => activeVisibility[key] !== false).length
  }, [primaryKeys, activeVisibility])

  // Visibility toggling
  const toggleColumn = (key) => {
    const targetCol = columns.find((c) => c.key === key)
    const isPrimary = (targetCol?.priority || 'primary') === 'primary'
    const isCurrentlyVisible = activeVisibility[key] !== false

    if (isPrimary && isCurrentlyVisible && visiblePrimaryCount <= 1) {
      return
    }

    const next = { ...activeVisibility, [key]: !isCurrentlyVisible }
    if (!isVisibilityControlled) {
      setInternalVisibility(next)
    }
    onColumnVisibilityChange?.(next)
  }

  // Resets
  const defaultVisibilityMap = useMemo(
    () => getInitialVisibility(columns, defaultColumnVisibility),
    [columns, defaultColumnVisibility]
  )

  const isVisibilityDirty = useMemo(() => {
    return Object.keys(defaultVisibilityMap).some(
      (key) => Boolean(activeVisibility[key]) !== Boolean(defaultVisibilityMap[key])
    )
  }, [defaultVisibilityMap, activeVisibility])

  const isSorted = Boolean(activeSort && activeSort.key && activeSort.direction)

  const handleResetVisibility = () => {
    const defaults = getInitialVisibility(columns, defaultColumnVisibility)
    if (!isVisibilityControlled) {
      setInternalVisibility(defaults)
    }
    onColumnVisibilityChange?.(defaults)
  }

  const handleResetSort = () => {
    const next = resolvedDefaultSort || null
    if (!isSortControlled) {
      setInternalSort(next)
    }
    onSortChange?.(next)
  }

  const handleResetAll = () => {
    handleResetSort()
    handleResetVisibility()
  }

  // Header sort click
  const handleHeaderSort = (key) => {
    let next = null
    if (!activeSort || activeSort.key !== key) {
      next = { key, direction: 'asc' }
    } else if (activeSort.direction === 'asc') {
      next = { key, direction: 'desc' }
    } else if (activeSort.direction === 'desc') {
      next = null
    } else {
      next = { key, direction: 'asc' }
    }

    if (!isSortControlled) {
      setInternalSort(next)
    }
    onSortChange?.(next)
  }

  // Visible columns
  const visibleColumns = useMemo(() => {
    return columns.filter((col) => {
      if (activeVisibility[col.key] !== undefined) {
        return !!activeVisibility[col.key]
      }
      if (typeof col.defaultVisible === 'boolean') {
        return col.defaultVisible
      }
      return col.priority !== 'optional'
    })
  }, [columns, activeVisibility])

  // Sorted rows
  const sortedRows = useMemo(() => {
    if (!rows || rows.length === 0 || !activeSort || !activeSort.direction) {
      return rows || []
    }

    const col = columns.find((c) => c.key === activeSort.key)
    if (!col) return rows || []

    const indexedRows = rows.map((row, index) => ({ row, index }))

    indexedRows.sort((itemA, itemB) => {
      let result = 0
      if (typeof col.sortComparator === 'function') {
        result = col.sortComparator(itemA.row, itemB.row)
      } else {
        const getVal = col.sortAccessor || ((r) => r[col.key])
        const valA = getVal(itemA.row)
        const valB = getVal(itemB.row)
        result = compareValues(valA, valB)
      }

      if (activeSort.direction === 'desc') {
        result = -result
      }

      if (result === 0) {
        return itemA.index - itemB.index
      }
      return result
    })

    return indexedRows.map((item) => item.row)
  }, [rows, activeSort, columns])

  const shouldRenderToolbar =
    showToolbar &&
    columns.length > 0 &&
    (toolbar || enableColumnVisibility || isSorted || isVisibilityDirty)

  return (
    <div className="data-grid">
      {shouldRenderToolbar && (
        <div className="data-grid-toolbar" role="toolbar" aria-label="Table controls">
          {toolbar && <div className="data-grid-toolbar-start">{toolbar}</div>}
          <div className="data-grid-toolbar-actions">
            {isSorted && (
              <button
                type="button"
                className="button button-secondary button-xs data-grid-reset-sort-btn"
                onClick={handleResetSort}
              >
                Reset sorting
              </button>
            )}
            {(isSorted || isVisibilityDirty) && (
              <button
                type="button"
                className="button button-secondary button-xs data-grid-reset-btn"
                onClick={handleResetAll}
              >
                Reset
              </button>
            )}
            {enableColumnVisibility && (
              <div className="data-grid-menu-container" ref={menuRef}>
                <button
                  type="button"
                  className="button button-secondary button-xs data-grid-columns-btn"
                  aria-haspopup="menu"
                  aria-expanded={isMenuOpen}
                  onClick={() => setIsMenuOpen((prev) => !prev)}
                >
                  Columns
                </button>
                {isMenuOpen && (
                  <div className="data-grid-menu" role="menu">
                    {columns.map((col) => {
                      const isPrimary = (col.priority || 'primary') === 'primary'
                      const isChecked = activeVisibility[col.key] !== false
                      const cannotHide = isPrimary && isChecked && visiblePrimaryCount <= 1
                      return (
                        <label key={col.key} className="data-grid-menu-item">
                          <input
                            type="checkbox"
                            checked={isChecked}
                            disabled={cannotHide}
                            onChange={() => toggleColumn(col.key)}
                          />
                          <span>{typeof col.header === 'string' ? col.header : col.key}</span>
                        </label>
                      )
                    })}
                    <div className="data-grid-menu-footer">
                      <button
                        type="button"
                        className="button button-secondary button-xs"
                        onClick={handleResetVisibility}
                      >
                        Reset defaults
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <div
        className="data-grid-container"
        tabIndex={0}
        role="region"
        aria-label={ariaLabel}
      >
        <table className="data-grid-table">
          <colgroup>
            {visibleColumns.map((col) => {
              const priority = col.priority || 'primary'
              const colClasses = `col-priority-${priority} data-grid-col-${priority}`
              const colStyle = {
                ...(col.width ? { width: col.width } : {}),
                ...(col.minWidth ? { minWidth: col.minWidth } : {}),
              }
              return (
                <col
                  key={col.key}
                  className={colClasses}
                  style={Object.keys(colStyle).length > 0 ? colStyle : undefined}
                />
              )
            })}
          </colgroup>
          <thead>
            <tr>
              {visibleColumns.map((col) => {
                const priority = col.priority || 'primary'
                const headerClasses = [
                  col.align ? `text-${col.align}` : '',
                  `col-priority-${priority}`,
                  `data-grid-col-${priority}`,
                ]
                  .filter(Boolean)
                  .join(' ')

                const headerStyle = {
                  ...(col.width ? { width: col.width } : {}),
                  ...(col.minWidth ? { minWidth: col.minWidth } : {}),
                }

                const ariaSort = col.sortable
                  ? activeSort?.key === col.key
                    ? activeSort.direction === 'asc'
                      ? 'ascending'
                      : activeSort.direction === 'desc'
                        ? 'descending'
                        : 'none'
                    : 'none'
                  : undefined

                return (
                  <th
                    key={col.key}
                    scope="col"
                    style={Object.keys(headerStyle).length > 0 ? headerStyle : undefined}
                    className={headerClasses || undefined}
                    aria-sort={ariaSort}
                  >
                    {col.sortable ? (
                      <button
                        type="button"
                        className="data-grid-sort-button"
                        onClick={() => handleHeaderSort(col.key)}
                        aria-label={`Sort by ${typeof col.header === 'string' ? col.header : col.key}`}
                      >
                        <span className="data-grid-header-text">{col.header}</span>
                        <span className="data-grid-sort-indicator" aria-hidden="true">
                          {activeSort?.key === col.key
                            ? activeSort.direction === 'asc'
                              ? ' ↑'
                              : ' ↓'
                            : ' ↕'}
                        </span>
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {isLoading && (!sortedRows || sortedRows.length === 0) ? (
              <LoadingRows columns={visibleColumns} count={loadingRowCount} />
            ) : sortedRows && sortedRows.length > 0 ? (
              sortedRows.map((row, index) => {
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
                    {visibleColumns.map((col) => {
                      const rawValue = col.render ? col.render(row, index) : row[col.key]
                      const titleText =
                        typeof rawValue === 'string' || typeof rawValue === 'number'
                          ? String(rawValue)
                          : typeof row[col.key] === 'string' || typeof row[col.key] === 'number'
                            ? String(row[col.key])
                            : undefined
                      const priority = col.priority || 'primary'
                      const cellClasses = [
                        'data-grid-cell',
                        col.align ? `text-${col.align}` : '',
                        `col-priority-${priority}`,
                        `data-grid-col-${priority}`,
                        col.wrap ? 'data-grid-cell-wrap' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')

                      return (
                        <td
                          key={col.key}
                          className={cellClasses}
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
                <td colSpan={visibleColumns.length || 1} className="data-grid-empty-cell">
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
    </div>
  )
}
