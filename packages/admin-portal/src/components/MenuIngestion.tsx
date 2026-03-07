import { useState } from 'react'
import * as XLSX from 'xlsx'
import * as api from '../services/api'
import { MenuUploadRow } from '../types'

interface MenuIngestionProps {
    restaurantId: string;
    onSuccess: () => void;
}

export default function MenuIngestion({ restaurantId, onSuccess }: MenuIngestionProps) {
    const [uploading, setUploading] = useState(false)
    const [preview, setPreview] = useState<MenuUploadRow[]>([])
    const [message, setMessage] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return;

        const reader = new FileReader()
        reader.onload = (evt) => {
            const bstr = evt.target?.result
            const wb = XLSX.read(bstr, { type: 'binary' })
            const wsname = wb.SheetNames[0]
            const ws = wb.Sheets[wsname]
            const data = XLSX.utils.sheet_to_json(ws) as MenuUploadRow[]

            setPreview(data)
            setMessage(null)
            setError(null)
        }
        reader.readAsBinaryString(file)
    }

    const handleImport = async () => {
        if (preview.length === 0) return;
        if (!confirm(`Ready to import ${preview.length} items? This will overwrite the existing menu.`)) return;

        setUploading(true)
        setMessage(null)
        setError(null)
        try {
            // Normalize keys to lowercase
            const normalizedItems = preview.map((row: MenuUploadRow) => {
                const newRow: Record<string, string | number | undefined> = {}
                Object.keys(row).forEach(key => {
                    let val = row[key]
                    const lowerKey = key.toLowerCase()

                    // Cleanup Price if it's a string
                    if (lowerKey === 'price' && typeof val === 'string') {
                        val = val.replace('$', '').replace(',', '').trim()
                    }

                    newRow[lowerKey] = val
                })
                return newRow
            })

            await api.importMenu(restaurantId, normalizedItems)
            setMessage(`Menu imported successfully! (${preview.length} items)`)
            setPreview([])
            onSuccess()
        } catch (e: unknown) {
            console.error("Network/Parsing Error:", e)
            setError(`Import failed: ${e instanceof Error ? e.message : "Network Error"}`)
        } finally {
            setUploading(false)
        }
    }

    return (
        <div style={{ marginTop: '2rem', padding: '1rem', border: '1px solid #ddd', borderRadius: '8px', background: '#f9fafb' }}>
            <h3>Menu Ingestion</h3>
            <p style={{ fontSize: '0.9em', color: '#666' }}>
                Upload a <strong>CSV or Excel file (.csv, .xlsx, .xls)</strong> with columns: <strong>Category, Name, Description, Price</strong>.
            </p>

            {message && <div style={{ color: '#15803d', background: '#f0fdf4', padding: '0.75rem', borderRadius: '6px', marginBottom: '0.75rem' }}>{message}</div>}
            {error && <div style={{ color: '#b91c1c', background: '#fef2f2', padding: '0.75rem', borderRadius: '6px', marginBottom: '0.75rem' }}>{error}</div>}

            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', margin: '1rem 0' }}>
                <input
                    type="file"
                    accept=".csv,.xlsx,.xls"
                    onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file && !file.name.toLowerCase().match(/\.(csv|xlsx|xls)$/)) {
                            setError("Please upload a .csv, .xlsx, or .xls file only.")
                            e.target.value = '' // Reset
                            return
                        }
                        setError(null)
                        handleFileUpload(e)
                    }}
                />
                {preview.length > 0 && (
                    <button
                        onClick={handleImport}
                        disabled={uploading}
                        className="btn btn-primary"
                    >
                        {uploading ? 'Importing...' : `Import ${preview.length} Items`}
                    </button>
                )}
            </div>

            {preview.length > 0 && (
                <div style={{ maxHeight: '200px', overflowY: 'auto', background: 'white', padding: '0.5rem', border: '1px solid #eee' }}>
                    <table style={{ width: '100%', fontSize: '0.85em', textAlign: 'left' }}>
                        <thead>
                            <tr style={{ background: '#f3f4f6' }}>
                                <th>Category</th>
                                <th>Name</th>
                                <th>Price</th>
                            </tr>
                        </thead>
                        <tbody>
                            {preview.slice(0, 5).map((row, i) => (
                                <tr key={i}>
                                    <td>{row.Category || row.category}</td>
                                    <td>{row.Name || row.name}</td>
                                    <td>{row.Price || row.price}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {preview.length > 5 && <p style={{ textAlign: 'center', fontSize: '0.8em', color: '#888' }}>...and {preview.length - 5} more</p>}
                </div>
            )}
        </div>
    )
}
