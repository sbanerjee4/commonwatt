import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { LandingPage } from './pages/LandingPage'
import { SignInPage } from './pages/SignInPage'
import { UtilityPage } from './pages/UtilityPage'
import { BuildingPage } from './pages/BuildingPage'
import { RequireRole } from './components/RequireRole'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/signin" element={<SignInPage />} />
          <Route
            path="/utility"
            element={
              <RequireRole role="utility">
                <UtilityPage />
              </RequireRole>
            }
          />
          <Route
            path="/building"
            element={
              <RequireRole role="facility">
                <BuildingPage />
              </RequireRole>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
