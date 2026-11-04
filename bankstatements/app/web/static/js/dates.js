/**
 * Date formatting utilities.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatDate(val) {
  if (!val || val === 'null' || val === 'None') {
    return '—';
  }

  const s = String(val).trim();
  // Expecting 'YYYY-MM-DD' or ISO timestamp
  const dateStr = s.substring(0, 10);
  const parts = dateStr.split('-');
  if (parts.length === 3) {
    const year = parts[0];
    const monthIdx = parseInt(parts[1], 10) - 1;
    const day = parts[2];
    if (monthIdx >= 0 && monthIdx < 12) {
      return `${day} ${MONTHS[monthIdx]} ${year}`;
    }
  }

  return s;
}

