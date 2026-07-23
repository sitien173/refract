import React from 'react';
import styles from '../styles/app.module.css';

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render: (row: T) => React.ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  caption: string | React.ReactNode;
  columns: Column<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  className?: string;
  onRowClick?: (row: T) => void;
  selectedRowKey?: string;
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  getRowKey,
  className,
  onRowClick,
  selectedRowKey,
}: DataTableProps<T>): React.ReactElement {
  const captionText = typeof caption === 'string' ? caption : 'Data Table';

  return (
    <div
      className={`${styles.tableOverflowRegion} ${className || ''}`.trim()}
      tabIndex={0}
      role="region"
      aria-label={captionText}
    >
      <table className={styles.dataTable}>
        <caption className={styles.tableCaption}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col" className={col.className}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = getRowKey(row);
            const isSelected = selectedRowKey !== undefined && selectedRowKey === key;
            const rowClassName = `${styles.tableRow} ${
              onRowClick ? styles.tableRowClickable : ''
            } ${isSelected ? styles.tableRowSelected : ''}`.trim();

            return (
              <tr
                key={key}
                className={rowClassName}
                onClick={(e) => {
                  if (!onRowClick) return;
                  const target = e.target as HTMLElement | null;
                  if (
                    target &&
                    target.closest('button, a, input, select, textarea, [role="button"]')
                  ) {
                    return;
                  }
                  onRowClick(row);
                }}
              >
                {columns.map((col) => (
                  <td key={`${key}-${col.key}`} className={col.className}>
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
