import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

// Ein Client für die gesamte App-Lebenszeit.
// Defaults sind bewusst konservativer als die TanStack-Defaults:
// - staleTime 5 min: Jahresdaten ändern sich selten, weniger Refetches
// - refetchOnWindowFocus aus: in der Lehre wirkt das ablenkend, im
//   echten Dashboard wäre 'true' sinnvoller
// - retry 1: Fehler schneller sichtbar machen, statt 3-mal still neu zu versuchen
const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 5 * 60 * 1000,
            refetchOnWindowFocus: false,
            retry: 1,
        },
    },
})

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <QueryClientProvider client={queryClient}>
            <BrowserRouter>
                <App />
            </BrowserRouter>
        </QueryClientProvider>
    </StrictMode>,
)