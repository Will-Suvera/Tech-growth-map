import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MapSearch, { searchPractices } from './MapSearch'
import { MOCK_PRACTICES } from '../test/fixtures'

describe('searchPractices', () => {
  it('returns nothing for an empty query', () => {
    expect(searchPractices(MOCK_PRACTICES, '')).toEqual([])
    expect(searchPractices(MOCK_PRACTICES, '   ')).toEqual([])
  })

  it('tolerates empty/undefined practices and rows with missing fields', () => {
    expect(searchPractices([], 'x')).toEqual([])
    expect(searchPractices(undefined, 'x')).toEqual([])
    expect(() => searchPractices([{ ods: 'A001' }], 'a001')).not.toThrow()
    expect(searchPractices([{ ods: 'A001' }], 'a001')[0].ods).toBe('A001')
  })

  it('matches an exact ODS code first', () => {
    const r = searchPractices(MOCK_PRACTICES, 'a003')
    expect(r[0].ods).toBe('A003')
  })

  it('matches by case-insensitive name substring', () => {
    const r = searchPractices(MOCK_PRACTICES, 'practice 4')
    expect(r.some(p => p.ods === 'A004')).toBe(true)
  })

  it('matches a postcode ignoring spaces', () => {
    const r = searchPractices(MOCK_PRACTICES, 'sw1a1aa')
    expect(r[0].ods).toBe('A001')
  })

  it('respects the result limit', () => {
    expect(searchPractices(MOCK_PRACTICES, 'practice', 2)).toHaveLength(2)
  })
})

describe('MapSearch component', () => {
  it('starts collapsed and expands on click', () => {
    render(<MapSearch practices={MOCK_PRACTICES} onSelect={() => {}} />)
    expect(screen.queryByRole('combobox')).toBeNull()
    fireEvent.click(screen.getByLabelText('Search practices'))
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('calls onSelect with the chosen practice', () => {
    const onSelect = vi.fn()
    render(<MapSearch practices={MOCK_PRACTICES} onSelect={onSelect} />)
    fireEvent.click(screen.getByLabelText('Search practices'))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'A002' } })
    fireEvent.mouseDown(screen.getByText('Test Practice 2'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ ods: 'A002' }))
  })

  it('selects the active result on Enter', () => {
    const onSelect = vi.fn()
    render(<MapSearch practices={MOCK_PRACTICES} onSelect={onSelect} />)
    fireEvent.click(screen.getByLabelText('Search practices'))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'N1 1DD' } })
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ ods: 'A004' }))
  })

  it('moves the active option with ArrowDown', () => {
    render(<MapSearch practices={MOCK_PRACTICES} onSelect={() => {}} />)
    fireEvent.click(screen.getByLabelText('Search practices'))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'practice' } })
    const optsBefore = screen.getAllByRole('option')
    expect(optsBefore[0]).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' })
    const optsAfter = screen.getAllByRole('option')
    expect(optsAfter[1]).toHaveAttribute('aria-selected', 'true')
    expect(optsAfter[0]).toHaveAttribute('aria-selected', 'false')
  })

  it('closes on Escape and returns focus to the trigger', () => {
    render(<MapSearch practices={MOCK_PRACTICES} onSelect={() => {}} />)
    fireEvent.click(screen.getByLabelText('Search practices'))
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' })
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(document.activeElement).toBe(screen.getByLabelText('Search practices'))
  })

  it('closes via the × button', () => {
    render(<MapSearch practices={MOCK_PRACTICES} onSelect={() => {}} />)
    fireEvent.click(screen.getByLabelText('Search practices'))
    fireEvent.click(screen.getByLabelText('Close search'))
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('shows an empty state when nothing matches', () => {
    render(<MapSearch practices={MOCK_PRACTICES} onSelect={() => {}} />)
    fireEvent.click(screen.getByLabelText('Search practices'))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'zzzzz' } })
    expect(screen.getByText('No matching practice')).toBeInTheDocument()
  })
})
