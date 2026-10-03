/** SCR-03 Overview — placeholder until M2. */
import { useMe } from "@/api/queries/me"
import { BaseUrlCard, PageHeader } from "@/components/mockan"

export function OverviewPage() {
  const me = useMe()
  if (!me.data?.slug) return null
  return (
    <div className="space-y-8">
      <PageHeader title="Overview" />
      <BaseUrlCard slug={me.data.slug} />
    </div>
  )
}
