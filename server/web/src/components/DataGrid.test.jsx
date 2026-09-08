import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import DataGrid from './DataGrid'

describe('DataGrid - Task 1: Column metadata and backward compatibility', () => {
  const basicColumns = [
    { key: 'id', header: 'ID', width: '100px' },
    { key: 'name', header: 'Name', align: 'left' },
  ]

  const basicRows = [
    { id: '1', name: 'Alpha' },
    { id: '2', name: 'Beta' },
  ]

  it('preserves backward compatibility with existing column definitions', () => {
    render(<DataGrid columns={basicColumns} rows={basicRows} />)

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'ID' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('supports priority metadata with optional hidden by default and priority classes applied', () => {
    const columnsWithPriority = [
      { key: 'id', header: 'ID', priority: 'primary' },
      { key: 'desc', header: 'Description', priority: 'secondary', wrap: true },
      { key: 'tag', header: 'Tag', priority: 'tertiary' },
      { key: 'extra', header: 'Extra', priority: 'optional' },
    ]
    const rows = [{ id: '1', desc: 'A long description', tag: 'v1', extra: 'secret' }]

    render(<DataGrid columns={columnsWithPriority} rows={rows} />)

    // Primary, secondary, tertiary headers are rendered by default
    expect(screen.getByRole('columnheader', { name: 'ID' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Description' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Tag' })).toBeInTheDocument()
    // Optional column should be hidden by default
    expect(screen.queryByRole('columnheader', { name: 'Extra' })).not.toBeInTheDocument()
    expect(screen.queryByText('secret')).not.toBeInTheDocument()

    // Check classes on headers and cells
    const idHeader = screen.getByRole('columnheader', { name: 'ID' })
    expect(idHeader.className).toMatch(/col-priority-primary/)

    const descCell = screen.getByText('A long description').closest('td')
    expect(descCell.className).toMatch(/col-priority-secondary/)
    expect(descCell.className).toMatch(/data-grid-cell-wrap/)
  })

  it('applies minWidth and width metadata to col elements', () => {
    const columns = [
      { key: 'id', header: 'ID', width: '120px', minWidth: '80px' },
      { key: 'name', header: 'Name', width: '200px' },
    ]
    const { container } = render(<DataGrid columns={columns} rows={[{ id: '1', name: 'Alpha' }]} />)

    const cols = container.querySelectorAll('colgroup col')
    expect(cols[0]).toHaveStyle({ width: '120px', minWidth: '80px' })
    expect(cols[1]).toHaveStyle({ width: '200px' })
  })
})

describe('DataGrid - Task 2: Stable controlled and uncontrolled table state', () => {
  const columns = [
    { key: 'id', header: 'ID', sortable: true },
    { key: 'score', header: 'Score', sortable: true },
    { key: 'category', header: 'Category' },
  ]

  it('cycles sort state through ascending, descending, and unsorted while updating aria-sort', () => {
    const rows = [
      { id: 'b', score: 10, category: 'cat1' },
      { id: 'a', score: 20, category: 'cat2' },
      { id: 'c', score: 15, category: 'cat3' },
    ]

    render(<DataGrid columns={columns} rows={rows} />)

    const idHeader = screen.getByRole('columnheader', { name: /ID/i })
    const sortBtn = screen.getByRole('button', { name: /Sort by ID/i })

    // Initially unsorted
    expect(idHeader).toHaveAttribute('aria-sort', 'none')
    const cellsInitial = screen.getAllByRole('cell').map((c) => c.textContent)
    expect(cellsInitial[0]).toBe('b')

    // First click: ascending
    fireEvent.click(sortBtn)
    expect(idHeader).toHaveAttribute('aria-sort', 'ascending')
    let cells = screen.getAllByRole('cell').map((c) => c.textContent)
    expect(cells[0]).toBe('a')
    expect(cells[3]).toBe('b')
    expect(cells[6]).toBe('c')

    // Second click: descending
    fireEvent.click(sortBtn)
    expect(idHeader).toHaveAttribute('aria-sort', 'descending')
    cells = screen.getAllByRole('cell').map((c) => c.textContent)
    expect(cells[0]).toBe('c')
    expect(cells[3]).toBe('b')
    expect(cells[6]).toBe('a')

    // Third click: unsorted
    fireEvent.click(sortBtn)
    expect(idHeader).toHaveAttribute('aria-sort', 'none')
    cells = screen.getAllByRole('cell').map((c) => c.textContent)
    expect(cells[0]).toBe('b')
  })

  it('preserves source order for equal values (stable sort)', () => {
    const rows = [
      { id: 'item-1', score: 10, tieBreaker: 'first' },
      { id: 'item-2', score: 20, tieBreaker: 'second' },
      { id: 'item-3', score: 10, tieBreaker: 'third' },
      { id: 'item-4', score: 10, tieBreaker: 'fourth' },
    ]

    const customCols = [
      { key: 'score', header: 'Score', sortable: true },
      { key: 'tieBreaker', header: 'Tie' },
    ]

    render(<DataGrid columns={customCols} rows={rows} />)

    const scoreSortBtn = screen.getByRole('button', { name: /Sort by Score/i })

    // Sort ascending by score: items 1, 3, 4 all have score 10 and must remain in order 1, 3, 4
    fireEvent.click(scoreSortBtn)
    const tieCells = screen.getAllByRole('cell')
      .filter((_, i) => i % 2 === 1)
      .map((c) => c.textContent)

    expect(tieCells).toEqual(['first', 'third', 'fourth', 'second'])
  })

  it('does not mutate the source rows array', () => {
    const originalRows = Object.freeze([
      Object.freeze({ id: 'z', score: 100 }),
      Object.freeze({ id: 'a', score: 50 }),
    ])

    const copy = [...originalRows]

    render(<DataGrid columns={columns} rows={originalRows} />)

    const sortBtn = screen.getByRole('button', { name: /Sort by ID/i })
    fireEvent.click(sortBtn)

    // Ensure original rows array was not mutated in place
    expect(originalRows[0].id).toBe('z')
    expect(originalRows[1].id).toBe('a')
    expect(originalRows).toEqual(copy)
  })

  it('handles empty values (null, undefined, empty string) consistently in sorting', () => {
    const rowsWithEmpties = [
      { id: '1', score: null },
      { id: '2', score: 50 },
      { id: '3', score: '' },
      { id: '4', score: 10 },
      { id: '5', score: undefined },
    ]

    render(<DataGrid columns={columns} rows={rowsWithEmpties} />)

    const scoreBtn = screen.getByRole('button', { name: /Sort by Score/i })

    // Ascending: defined values 10, 50 first, empty values at the end
    fireEvent.click(scoreBtn)
    const ascRows = screen.getAllByRole('row').slice(1) // exclude header row
    const ascIds = ascRows.map((r) => r.querySelectorAll('td')[0].textContent)

    expect(ascIds.slice(0, 2)).toEqual(['4', '2'])
    expect(ascIds.slice(2)).toEqual(['1', '3', '5'])
  })

  it('supports controlled sort state via sort and onSortChange', () => {
    const rows = [
      { id: 'alpha', score: 10 },
      { id: 'beta', score: 20 },
    ]
    const onSortChange = vi.fn()

    const { rerender } = render(
      <DataGrid
        columns={columns}
        rows={rows}
        sort={{ key: 'id', direction: 'desc' }}
        onSortChange={onSortChange}
      />
    )

    const idHeader = screen.getByRole('columnheader', { name: /ID/i })
    expect(idHeader).toHaveAttribute('aria-sort', 'descending')

    // Clicking calls onSortChange with null (cycle from desc to null)
    const sortBtn = screen.getByRole('button', { name: /Sort by ID/i })
    fireEvent.click(sortBtn)
    expect(onSortChange).toHaveBeenCalledWith(null)

    // Updating controlled prop updates rendered rows and aria-sort
    rerender(
      <DataGrid
        columns={columns}
        rows={rows}
        sort={{ key: 'id', direction: 'asc' }}
        onSortChange={onSortChange}
      />
    )
    expect(idHeader).toHaveAttribute('aria-sort', 'ascending')
    const firstCell = screen.getAllByRole('cell')[0]
    expect(firstCell.textContent).toBe('alpha')
  })

  it('supports controlled and uncontrolled column visibility', () => {
    const rows = [{ id: '1', score: 10, category: 'tech' }]
    const onVisibilityChange = vi.fn()

    // Controlled: score hidden
    const { rerender } = render(
      <DataGrid
        columns={columns}
        rows={rows}
        columnVisibility={{ id: true, score: false, category: true }}
        onColumnVisibilityChange={onVisibilityChange}
      />
    )

    expect(screen.getByRole('columnheader', { name: /ID/i })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /Score/i })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Category/i })).toBeInTheDocument()

    // Rerender controlled: show score, hide category
    rerender(
      <DataGrid
        columns={columns}
        rows={rows}
        columnVisibility={{ id: true, score: true, category: false }}
        onColumnVisibilityChange={onVisibilityChange}
      />
    )

    expect(screen.getByRole('columnheader', { name: /Score/i })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /Category/i })).not.toBeInTheDocument()
  })
})

describe('DataGrid - Task 3: Accessible controls, reset behavior, and row spanning', () => {
  const columns = [
    { key: 'id', header: 'ID', priority: 'primary', sortable: true },
    { key: 'title', header: 'Title', priority: 'primary' },
    { key: 'env', header: 'Environment', priority: 'secondary' },
    { key: 'notes', header: 'Notes', priority: 'optional' },
  ]

  const rows = [
    { id: '1', title: 'Task A', env: 'prod', notes: 'Urgent' },
    { id: '2', title: 'Task B', env: 'dev', notes: 'Later' },
  ]

  it('renders columns menu and allows toggling column visibility', () => {
    render(<DataGrid columns={columns} rows={rows} />)

    const columnsBtn = screen.getByRole('button', { name: /Columns/i })
    expect(columnsBtn).toHaveAttribute('aria-expanded', 'false')

    // Open menu
    fireEvent.click(columnsBtn)
    expect(columnsBtn).toHaveAttribute('aria-expanded', 'true')

    // Optional column 'Notes' is unchecked by default
    const notesCheckbox = screen.getByRole('checkbox', { name: /Notes/i })
    expect(notesCheckbox).not.toBeChecked()

    // Toggle Notes visible
    fireEvent.click(notesCheckbox)
    expect(notesCheckbox).toBeChecked()
    expect(screen.getByRole('columnheader', { name: /Notes/i })).toBeInTheDocument()
    expect(screen.getByText('Urgent')).toBeInTheDocument()

    // Close menu with Escape
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(columnsBtn).toHaveAttribute('aria-expanded', 'false')
  })

  it('prevents users from hiding every primary column', () => {
    render(<DataGrid columns={columns} rows={rows} />)

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }))

    const idCheckbox = screen.getByRole('checkbox', { name: /ID/i })
    const titleCheckbox = screen.getByRole('checkbox', { name: /Title/i })

    expect(idCheckbox).not.toBeDisabled()
    expect(titleCheckbox).not.toBeDisabled()

    // Uncheck 'id' - now 'title' is the only visible primary column
    fireEvent.click(idCheckbox)
    expect(idCheckbox).not.toBeChecked()
    expect(titleCheckbox).toBeDisabled()

    // Clicking disabled titleCheckbox does nothing
    fireEvent.click(titleCheckbox)
    expect(titleCheckbox).toBeChecked()
    expect(screen.getByRole('columnheader', { name: /Title/i })).toBeInTheDocument()
  })

  it('restores default sorting and visibility on reset', () => {
    render(<DataGrid columns={columns} rows={rows} />)

    const idSortBtn = screen.getByRole('button', { name: /Sort by ID/i })
    fireEvent.click(idSortBtn) // sort asc
    expect(screen.getByRole('columnheader', { name: /ID/i })).toHaveAttribute('aria-sort', 'ascending')

    // Reset sorting button appears
    const resetSortBtn = screen.getByRole('button', { name: /Reset sorting/i })
    expect(resetSortBtn).toBeInTheDocument()

    // Change column visibility
    fireEvent.click(screen.getByRole('button', { name: /Columns/i }))
    const envCheckbox = screen.getByRole('checkbox', { name: /Environment/i })
    fireEvent.click(envCheckbox) // hide secondary column
    expect(screen.queryByRole('columnheader', { name: /Environment/i })).not.toBeInTheDocument()

    // Reset all button appears and restores both
    const resetAllBtn = screen.getByRole('button', { name: /^Reset$/i })
    fireEvent.click(resetAllBtn)

    expect(screen.getByRole('columnheader', { name: /ID/i })).toHaveAttribute('aria-sort', 'none')
    expect(screen.getByRole('columnheader', { name: /Environment/i })).toBeInTheDocument()
  })

  it('empty row spans exactly the number of visible columns', () => {
    const { rerender } = render(<DataGrid columns={columns} rows={[]} />)

    // Initially 3 visible columns (id, title, env; notes is optional/hidden)
    let emptyCell = screen.getByText('No records found.').closest('td')
    expect(emptyCell).toHaveAttribute('colspan', '3')

    // Hide Environment
    rerender(
      <DataGrid
        columns={columns}
        rows={[]}
        columnVisibility={{ id: true, title: true, env: false, notes: false }}
      />
    )

    emptyCell = screen.getByText('No records found.').closest('td')
    expect(emptyCell).toHaveAttribute('colspan', '2')
  })

  it('loading rows span visible columns when isLoading is true', () => {
    const { container } = render(
      <DataGrid
        columns={columns}
        rows={[]}
        isLoading={true}
        loadingRowCount={2}
      />
    )

    // 2 loading rows, each having 3 cells (for 3 default visible columns)
    const loadingRows = container.querySelectorAll('.data-grid-row-loading')
    expect(loadingRows).toHaveLength(2)
    expect(loadingRows[0].querySelectorAll('td')).toHaveLength(3)
  })
})

describe('DataGrid - Task 4: Row activation, custom sorters, and recovery actions', () => {
  const columns = [
    { key: 'id', header: 'ID', sortable: true },
    {
      key: 'metric',
      header: 'Metric',
      sortable: true,
      sortAccessor: (row) => row.nested?.value,
    },
    {
      key: 'custom',
      header: 'Custom',
      sortable: true,
      sortComparator: (a, b) => a.customOrder - b.customOrder,
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (row) => (
        <button type="button" onClick={(e) => e.stopPropagation()}>
          Row action {row.id}
        </button>
      ),
    },
  ]

  const rows = [
    { id: '1', nested: { value: 30 }, customOrder: 3 },
    { id: '2', nested: { value: 10 }, customOrder: 1 },
    { id: '3', nested: { value: 20 }, customOrder: 2 },
  ]

  it('handles row activation via pointer click and keyboard, ignoring modifier keys and nested controls', () => {
    const onRowClick = vi.fn()
    render(<DataGrid columns={columns} rows={rows} onRowClick={onRowClick} />)

    const tableRows = screen.getAllByRole('row').slice(1) // exclude header
    expect(tableRows[0]).toHaveClass('data-grid-row-interactive')
    expect(tableRows[0]).toHaveAttribute('tabindex', '0')

    // Click on row triggers onRowClick
    fireEvent.click(tableRows[0])
    expect(onRowClick).toHaveBeenCalledTimes(1)
    expect(onRowClick).toHaveBeenCalledWith(rows[0], expect.any(Object))

    // Click with ctrlKey is ignored
    fireEvent.click(tableRows[0], { ctrlKey: true })
    expect(onRowClick).toHaveBeenCalledTimes(1)

    // Click with metaKey is ignored
    fireEvent.click(tableRows[0], { metaKey: true })
    expect(onRowClick).toHaveBeenCalledTimes(1)

    // Click inside button in row is ignored
    const rowButton = screen.getByRole('button', { name: 'Row action 1' })
    fireEvent.click(rowButton)
    expect(onRowClick).toHaveBeenCalledTimes(1)

    // Keyboard activation via Enter
    fireEvent.keyDown(tableRows[1], { key: 'Enter' })
    expect(onRowClick).toHaveBeenCalledTimes(2)
    expect(onRowClick).toHaveBeenCalledWith(rows[1], expect.any(Object))

    // Keyboard activation via Space
    fireEvent.keyDown(tableRows[2], { key: ' ' })
    expect(onRowClick).toHaveBeenCalledTimes(3)
    expect(onRowClick).toHaveBeenCalledWith(rows[2], expect.any(Object))
  })

  it('supports custom sortAccessor and sortComparator', () => {
    render(<DataGrid columns={columns} rows={rows} />)

    // Sort by metric (sortAccessor: row.nested.value)
    const metricSortBtn = screen.getByRole('button', { name: /Sort by Metric/i })
    fireEvent.click(metricSortBtn) // asc: 10 (id: 2), 20 (id: 3), 30 (id: 1)

    let firstCell = screen.getAllByRole('cell')[0]
    expect(firstCell.textContent).toBe('2')

    // Sort by custom (sortComparator: a.customOrder - b.customOrder)
    const customSortBtn = screen.getByRole('button', { name: /Sort by Custom/i })
    fireEvent.click(customSortBtn) // asc: 1 (id: 2), 2 (id: 3), 3 (id: 1)

    firstCell = screen.getAllByRole('cell')[0]
    expect(firstCell.textContent).toBe('2')
  })

  it('renders recovery action in empty state', () => {
    const onClear = vi.fn()
    render(
      <DataGrid
        columns={columns}
        rows={[]}
        emptyMessage="No matching items."
        recoveryAction={<button type="button" onClick={onClear}>Clear filters</button>}
      />
    )

    expect(screen.getByText('No matching items.')).toBeInTheDocument()
    const clearBtn = screen.getByRole('button', { name: 'Clear filters' })
    expect(clearBtn).toBeInTheDocument()
    fireEvent.click(clearBtn)
    expect(onClear).toHaveBeenCalled()
  })

  it('renders custom toolbar slot and supports hiding toolbar via showToolbar=false', () => {
    const { rerender } = render(
      <DataGrid
        columns={columns}
        rows={rows}
        toolbar={<div data-testid="custom-filter">Filter input</div>}
      />
    )

    expect(screen.getByTestId('custom-filter')).toBeInTheDocument()

    rerender(
      <DataGrid
        columns={columns}
        rows={rows}
        showToolbar={false}
      />
    )

    expect(screen.queryByRole('toolbar')).not.toBeInTheDocument()
  })
})



