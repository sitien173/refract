import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import fs from 'fs';
import path from 'path';
import { DataTable } from './DataTable';

interface TestItem {
  id: string;
  name: string;
  value: number;
}

describe('DataTable', () => {
  const items: TestItem[] = [
    { id: '1', name: 'Item One', value: 10 },
    { id: '2', name: 'Item Two', value: 20 },
  ];

  const columns = [
    { key: 'name', header: 'Name', render: (item: TestItem) => item.name },
    { key: 'value', header: 'Value', render: (item: TestItem) => item.value },
  ];

  it('renders semantic table elements, caption, scoped headers, and focusable overflow region', () => {
    const { container } = render(
      <DataTable
        caption="Test Items Table"
        columns={columns}
        rows={items}
        getRowKey={(item) => item.id}
      />
    );

    const region = screen.getByRole('region', { name: 'Test Items Table' });
    expect(region).toBeTruthy();
    expect(region.getAttribute('tabindex')).toBe('0');

    expect(screen.getByText('Test Items Table')).toBeTruthy();

    const headers = screen.getAllByRole('columnheader');
    expect(headers.length).toBe(2);
    expect(headers[0].getAttribute('scope')).toBe('col');
    expect(headers[0].textContent).toBe('Name');
    expect(headers[1].textContent).toBe('Value');

    const rows = container.querySelectorAll('tbody tr');
    expect(rows.length).toBe(2);
    expect(rows[0].getAttribute('tabindex')).toBeNull();

    expect(screen.getByText('Item One')).toBeTruthy();
    expect(screen.getByText('Item Two')).toBeTruthy();
  });

  it('uses valid --bg-surface-hover token for table row hover/focus state', () => {
    const cssPath = path.resolve(__dirname, '../styles/app.module.css');
    const cssContent = fs.readFileSync(cssPath, 'utf8');
    expect(cssContent).toContain('--bg-surface-hover');
    expect(cssContent).not.toContain('--color-surface-hover');
  });

  it('supports optional onRowClick that fires on non-interactive cell content and ignores interactive descendants without making tr interactive in A11y tree', async () => {
    const fireEvent = (await import('@testing-library/react')).fireEvent;
    const handleRowClick = vi.fn();
    const handleButtonClick = vi.fn();

    const clickableColumns = [
      { key: 'name', header: 'Name', render: (item: TestItem) => item.name },
      {
        key: 'action',
        header: 'Action',
        render: (item: TestItem) => (
          <button type="button" onClick={handleButtonClick}>
            Action {item.id}
          </button>
        ),
      },
    ];

    const { container } = render(
      <DataTable
        caption="Clickable Table"
        columns={clickableColumns}
        rows={items}
        getRowKey={(item) => item.id}
        onRowClick={handleRowClick}
        selectedRowKey="1"
      />
    );

    const rows = container.querySelectorAll('tbody tr');
    expect(rows[0].getAttribute('role')).toBeNull();
    expect(rows[0].getAttribute('tabindex')).toBeNull();

    // Click non-interactive cell content
    const cellText = screen.getByText('Item One');
    fireEvent.click(cellText);
    expect(handleRowClick).toHaveBeenCalledTimes(1);
    expect(handleRowClick).toHaveBeenCalledWith(items[0]);

    // Click interactive button
    const btn = screen.getByRole('button', { name: 'Action 1' });
    fireEvent.click(btn);
    expect(handleButtonClick).toHaveBeenCalledTimes(1);
    // onRowClick should NOT have been called again
    expect(handleRowClick).toHaveBeenCalledTimes(1);
  });
});
