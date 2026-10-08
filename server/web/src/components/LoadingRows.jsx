export default function LoadingRows({ columns = [], count = 4 }) {
  const columnCount = columns.length || 1
  return (
    <>
      {Array.from({ length: count }, (_, rowIndex) => (
        <tr key={`loading-${rowIndex}`} className="data-grid-row data-grid-row-loading" aria-busy="true">
          {columns.length > 0 ? (
            columns.map((col, colIndex) => {
              const priority = col.priority || 'primary'
              const priorityClass = `col-priority-${priority} data-grid-col-${priority}`
              return (
                <td
                  key={col.key || colIndex}
                  className={`data-grid-cell ${priorityClass}`}
                  style={col.width ? { width: col.width } : undefined}
                >
                  <div className="skeleton-line" aria-hidden="true" />
                </td>
              )
            })
          ) : (
            <td colSpan={columnCount} className="data-grid-cell">
              <div className="skeleton-line" aria-hidden="true" />
            </td>
          )}
        </tr>
      ))}
    </>
  )
}

