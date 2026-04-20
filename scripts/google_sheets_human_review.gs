/**
 * Google Apps Script web app for ApplyPilot human-review rows.
 *
 * Setup:
 * 1. Create a Google Sheet and open Extensions -> Apps Script.
 * 2. Paste this file into the script editor.
 * 3. Set script properties:
 *    - SHEET_NAME = Human Review
 *    - APPLYPILOT_SECRET = same value as GOOGLE_SHEETS_WEBHOOK_SECRET
 * 4. Deploy -> New deployment -> Web app.
 * 5. Set execute as "Me" and access to "Anyone with the link".
 * 6. Copy the web app URL into GOOGLE_SHEETS_WEBHOOK_URL.
 */

function doPost(e) {
  const props = PropertiesService.getScriptProperties();
  const expectedSecret = props.getProperty('APPLYPILOT_SECRET') || '';
  const defaultSheetName = props.getProperty('SHEET_NAME') || 'Human Review';

  try {
    const payload = JSON.parse(e.postData.contents || '{}');
    const providedSecret = payload.secret || '';

    if (expectedSecret && providedSecret !== expectedSecret) {
      return jsonResponse({ ok: false, error: 'unauthorized' }, 401);
    }

    const rows = Array.isArray(payload.rows) ? payload.rows : [];
    const headers = Array.isArray(payload.columns) && payload.columns.length
      ? payload.columns
      : [
          'job_url',
          'application_url',
          'title',
          'source_site',
          'location',
          'fit_score',
          'score_reasoning',
          'human_review_reason',
          'cover_letter_text',
          'review_queue',
          'review_status',
          'review_owner',
          'human_notes',
          'discovered_at',
          'scored_at',
          'handoff_at',
          'updated_at',
        ];

    const preserveHumanColumns = ['review_status', 'review_owner', 'human_notes'];
    const sheets = {};
    const existingMaps = {};

    rows.forEach((row) => {
      const targetSheetName = row.review_queue || defaultSheetName;
      if (!sheets[targetSheetName]) {
        const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(targetSheetName)
          || SpreadsheetApp.getActiveSpreadsheet().insertSheet(targetSheetName);
        ensureHeaders(sheet, headers);
        sheets[targetSheetName] = sheet;
        existingMaps[targetSheetName] = loadExistingRows(sheet);
      }

      const sheet = sheets[targetSheetName];
      const existing = existingMaps[targetSheetName];
      const targetRow = existing[row.job_url];
      let values = headers.map((header) => {
        if (header === 'updated_at') return new Date().toISOString();
        if (header === 'review_status') return row[header] || 'pending';
        return row[header] || '';
      });

      if (targetRow) {
        const currentValues = sheet.getRange(targetRow, 1, 1, headers.length).getValues()[0];
        preserveHumanColumns.forEach((header) => {
          const idx = headers.indexOf(header);
          if (idx !== -1 && currentValues[idx]) {
            values[idx] = currentValues[idx];
          }
        });
        sheet.getRange(targetRow, 1, 1, headers.length).setValues([values]);
      } else {
        sheet.appendRow(values);
        existing[row.job_url] = sheet.getLastRow();
      }
    });

    return jsonResponse({ ok: true, synced: rows.length }, 200);
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) }, 500);
  }
}

function ensureHeaders(sheet, headers) {
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
    sheet.setFrozenRows(1);
    return;
  }

  const current = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  const matches = headers.every((header, idx) => current[idx] === header);
  if (!matches) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
  }
}

function loadExistingRows(sheet) {
  const map = {};
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return map;

  const values = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  values.forEach((row, index) => {
    const jobUrl = row[0];
    if (jobUrl) {
      map[jobUrl] = index + 2;
    }
  });
  return map;
}

function jsonResponse(payload, status) {
  return ContentService
    .createTextOutput(JSON.stringify({ status, ...payload }))
    .setMimeType(ContentService.MimeType.JSON);
}
