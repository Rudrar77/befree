/**
 * Money formatting utility implementing Indian Numbering System grouping.
 * CRITICAL RULE: Never uses Number() or parseFloat() on money strings!
 */

export function formatINR(val) {
  if (val === null || val === undefined || val === '') {
    return '—';
  }

  let s = String(val).trim();
  if (!s || s === 'null' || s === 'None' || s === '—') {
    return '—';
  }

  let isNegative = false;
  if (s.startsWith('-')) {
    isNegative = true;
    s = s.substring(1).trim();
  }

  let intPart = '';
  let decPart = '00';

  if (s.includes('.')) {
    const parts = s.split('.');
    intPart = parts[0];
    decPart = (parts[1] + '00').substring(0, 2);
  } else {
    intPart = s;
  }

  // Remove any non-digit characters from intPart
  intPart = intPart.replace(/\D/g, '');
  if (!intPart) {
    intPart = '0';
  }

  // Group Indian style: last 3 digits, then pairs of 2 digits
  let formattedInt = '';
  if (intPart.length <= 3) {
    formattedInt = intPart;
  } else {
    const last3 = intPart.substring(intPart.length - 3);
    let rest = intPart.substring(0, intPart.length - 3);
    const pairs = [];
    while (rest.length > 2) {
      pairs.push(rest.substring(rest.length - 2));
      rest = rest.substring(0, rest.length - 2);
    }
    if (rest.length > 0) {
      pairs.push(rest);
    }
    pairs.reverse();
    formattedInt = pairs.join(',') + ',' + last3;
  }

  const result = `₹${formattedInt}.${decPart}`;
  return isNegative ? `-${result}` : result;
}

