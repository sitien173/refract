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
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  getRowKey,
  className,
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
            return (
              <tr key={key} className={styles.tableRow}>
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
