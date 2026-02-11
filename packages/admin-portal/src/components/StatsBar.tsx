
import '../App.css' // Reuse styles for now

interface StatsBarProps {
    sentCount: number;
    activeCount: number;
    pendingCount: number;
}

export default function StatsBar({ sentCount, activeCount, pendingCount }: StatsBarProps) {
    return (
        <div className="stats-bar">
            <div className="stat-card new-orders">
                <span className="stat-value">{sentCount}</span>
                <span className="stat-label">🔔 New</span>
            </div>
            <div className="stat-card">
                <span className="stat-value">{activeCount}</span>
                <span className="stat-label">🔥 Active</span>
            </div>
            <div className="stat-card">
                <span className="stat-value">{pendingCount}</span>
                <span className="stat-label">⏳ Pending</span>
            </div>
        </div>
    )
}
