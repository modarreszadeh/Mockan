import { useState } from "react"
import { RouterProvider } from "react-router/dom"

import { Providers } from "./providers"
import { createQueryClient } from "./query-client"
import { createAppRouter } from "./router"

export function App() {
  const [queryClient] = useState(createQueryClient)
  const [router] = useState(createAppRouter)
  return (
    <Providers queryClient={queryClient}>
      <RouterProvider router={router} />
    </Providers>
  )
}
