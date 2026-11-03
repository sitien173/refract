import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// Vendored TDS stylesheets
import '../tds/tokens/fonts.css'
import '../tds/tokens/tokens.css'
import '../tds/Components/button/button.css'
import '../tds/Components/spinner/spinner.css'
import '../tds/Components/tabs/tabs.css'
import '../tds/Components/side-nav/side-nav.css'
import '../tds/Components/switch/switch.css'
import '../tds/Components/announcement/announcement.css'
import '../tds/Components/_shared/tag/tag.css'
import '../tds/Components/data-table/data-table.css'
import '../tds/Components/text-input/text-input.css'
import '../tds/Components/select/select.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
