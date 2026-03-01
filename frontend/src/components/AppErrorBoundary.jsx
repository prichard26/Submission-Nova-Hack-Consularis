import { Component } from 'react'

export default class AppErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    // Keep error reporting centralized for future monitoring integrations.
    console.error('Unhandled app error', error, info)
  }

  handleRetry = () => {
    this.setState({ hasError: false })
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <main className="app-error" role="alert">
        <h1>Something went wrong</h1>
        <p>Refresh the page to recover the current session.</p>
        <button type="button" onClick={this.handleRetry}>Reload</button>
      </main>
    )
  }
}
