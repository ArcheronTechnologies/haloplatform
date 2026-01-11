import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import { AuthProvider, RequireAuth } from './components/AuthProvider'
import Dashboard from './pages/Dashboard'
import Entities from './pages/Entities'
import EntityDetail from './pages/EntityDetail'
import Alerts from './pages/Alerts'
import AlertDetail from './pages/AlertDetail'
import Cases from './pages/Cases'
import CaseDetail from './pages/CaseDetail'
import Search from './pages/Search'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Demo from './pages/Demo'
import Network from './pages/Network'
import SARs from './pages/SARs'
import AuditLog from './pages/AuditLog'
import Users from './pages/Users'
import Documents from './pages/Documents'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />

        {/* Protected routes */}
        <Route
          path="/"
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="entities" element={<Entities />} />
          <Route path="entities/:id" element={<EntityDetail />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="alerts/:id" element={<AlertDetail />} />
          <Route path="cases" element={<Cases />} />
          <Route path="cases/:id" element={<CaseDetail />} />
          <Route path="sars" element={<SARs />} />
          <Route path="search" element={<Search />} />
          <Route path="audit" element={<AuditLog />} />
          <Route path="users" element={<Users />} />
          <Route path="documents" element={<Documents />} />
          <Route path="settings" element={<Settings />} />
          <Route path="network" element={<Network />} />
          <Route path="demo" element={<Demo />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
