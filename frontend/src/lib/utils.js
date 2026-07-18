export function timeAgo(dateString) {
  const now = Date.now()
  const past = new Date(dateString).getTime()
  const diff = Math.floor((now - past) / 1000)

  if (diff < 60) return '방금 전'
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`
  return `${Math.floor(diff / 86400)}일 전`
}

export function formatSeatLabel(seatId) {
  return seatId
}
