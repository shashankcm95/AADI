import React from 'react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError() {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        console.error('App Error:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div style={{ padding: '2rem', textAlign: 'center', fontFamily: 'system-ui, sans-serif' }}>
                    <h2>Something went wrong</h2>
                    <p>Please refresh the page to try again.</p>
                    <button
                        onClick={() => window.location.reload()}
                        style={{
                            marginTop: '1rem',
                            padding: '0.5rem 1.5rem',
                            borderRadius: '6px',
                            border: 'none',
                            background: '#1a73e8',
                            color: '#fff',
                            cursor: 'pointer',
                            fontSize: '1rem',
                        }}
                    >
                        Refresh
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

export default ErrorBoundary;
