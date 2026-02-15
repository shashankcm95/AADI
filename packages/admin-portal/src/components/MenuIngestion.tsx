import { useState } from 'react'
import * as XLSX from 'xlsx'
import { API_BASE_URL } from '../aws-exports'

interface MenuIngestionProps {
    restaurantId: string;
    token: string;
    onSuccess: () => void;
}

export default function MenuIngestion({ restaurantId, token, onSuccess }: MenuIngestionProps) {
    const [uploading, setUploading] = useState(false)
    const [preview, setPreview] = useState<any[]>([])

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return;

        const reader = new FileReader()
        reader.onload = (evt) => {
            const bstr = evt.target?.result
            const wb = XLSX.read(bstr, { type: 'binary' })
            const wsname = wb.SheetNames[0]
            const ws = wb.Sheets[wsname]
            const data = XLSX.utils.sheet_to_json(ws)
            console.log("Parsed Excel Data:", data)
            setPreview(data)
        }
        reader.readAsBinaryString(file)
    }

    const handleImport = async () => {
        if (preview.length === 0) return;
        if (!confirm(`Ready to import ${preview.length} items? This will overwrite the existing menu.`)) return;

        setUploading(true)
        try {
            // Transform data to match API expectation (lowercase keys if needed, but app.py expects payload.items)
            // app.py expects: { items: [ { name, price, description, category, ... } ] }
            // Excel columns: Name, Price, Description, Category (Case sensitive matching?)

            // Normalize keys to lowercase
            const normalizedItems = preview.map((row: any) => {
                const newRow: any = {}
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

            const res = await fetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/menu`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ items: normalizedItems })
            })

            if (res.ok) {
                alert("Menu imported successfully!")
                setPreview([])
                onSuccess()
            } else {
                const err = await res.json()
                const msg = err.error || err.message || 'Unknown error'
                console.error("Backend Error:", err)
                alert(`Import failed: ${msg}`)
            }
        } catch (e: any) {
            console.error("Network/Parsing Error:", e)
            alert(`Import failed: ${e.message || "Network Error"}`)
        } finally {
            setUploading(false)
        }
    }

    return (
        <div style={{ marginTop: '2rem', padding: '1rem', border: '1px solid #ddd', borderRadius: '8px', background: '#f9fafb' }}>
            <h3>Menu Ingestion</h3>
            <p style={{ fontSize: '0.9em', color: '#666' }}>
                Upload a <strong>CSV file (.csv)</strong> with columns: <strong>Category, Name, Description, Price</strong>.
            </p>

            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', margin: '1rem 0' }}>
                <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file && !file.name.toLowerCase().endsWith('.csv')) {
                            alert("Please upload a .csv file only.")
                            e.target.value = '' // Reset
                            return
                        }
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
                            {preview.slice(0, 5).map((row: any, i) => (
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
