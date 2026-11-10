/** 资料整理计划的纯展示辅助。 */

export function computeOrganizeReport(plans: any[]) {
  const list = plans || []
  const pendingPlans = list.filter((p: any) => p.status === 'ready')
  const failedPlans = list.filter((p: any) => p.status === 'failed')
  return {
    total: list.length,
    ready: list.filter((p: any) => p.status === 'applied').length,
    pending: pendingPlans.length,
    failed: failedPlans.length,
    pendingFiles: [...pendingPlans, ...failedPlans]
  }
}

export function countOrganizePlans(plans: any[], status: string): number {
  return (plans || []).filter((p) => p.status === status).length
}

export function planStatusText(status: string): string {
  return (
    {
      running: '进行中',
      ready: '待确认',
      applied: '已应用',
      rejected: '未通过',
      failed: '失败',
      rolled_back: '已回退'
    } as Record<string, string>
  )[status] || status
}

export function planStatusType(status: string): string {
  if (status === 'applied') return 'success'
  if (status === 'failed' || status === 'rejected') return 'danger'
  if (status === 'ready') return 'warning'
  return 'info'
}
