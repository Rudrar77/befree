/**
 * Multi-file upload module with drag-and-drop and validation.
 */

import { apiRequest, showToast } from './api.js';

export function initUploadComponent({
  dropzoneId = 'dropzone',
  fileInputId = 'fileInput',
  fileListId = 'fileList',
  uploadBtnId = 'uploadBtn',
  uploadAndProcessBtnId = 'uploadAndProcessBtn',
  onSuccess = () => {},
}) {
  const dropzone = document.getElementById(dropzoneId);
  const fileInput = document.getElementById(fileInputId);
  const fileList = document.getElementById(fileListId);
  const uploadBtn = document.getElementById(uploadBtnId);
  const uploadAndProcessBtn = document.getElementById(uploadAndProcessBtnId);
  const passwordModalElement = document.getElementById('pdfPasswordModal');
  const passwordForm = document.getElementById('pdfPasswordForm');
  const passwordInput = document.getElementById('pdfPasswordInput');
  const passwordMessage = document.getElementById('pdfPasswordMessage');

  if (!dropzone || !fileInput) return;

  let selectedFiles = [];
  const supportedExtensions = ['.pdf', '.jpg', '.jpeg', '.png'];
  let resolvePassword = null;
  const passwordModal = passwordModalElement && window.bootstrap
    ? window.bootstrap.Modal.getOrCreateInstance(passwordModalElement)
    : null;

  if (passwordForm && passwordModal && passwordInput && passwordMessage) {
    passwordForm.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!passwordInput.value) {
        passwordInput.focus();
        return;
      }
      const resolve = resolvePassword;
      resolvePassword = null;
      resolve(passwordInput.value);
      passwordModal.hide();
    });

    passwordModalElement.addEventListener('hidden.bs.modal', () => {
      if (resolvePassword) {
        const resolve = resolvePassword;
        resolvePassword = null;
        resolve(null);
      }
      passwordInput.value = '';
    });
  }

  function requestPdfPassword(filename, retry = false) {
    if (!passwordModal || !passwordInput || !passwordMessage) {
      showToast('The PDF password prompt is unavailable. Reload the page and try again.', 'danger');
      return Promise.resolve(null);
    }

    passwordMessage.textContent = retry
      ? `The password for "${filename}" was incorrect. Please try again.`
      : `"${filename}" is password-protected. Enter its password to continue.`;
    passwordInput.value = '';
    passwordModal.show();

    return new Promise((resolve) => {
      resolvePassword = resolve;
      passwordModalElement.addEventListener('shown.bs.modal', () => passwordInput.focus(), { once: true });
    });
  }

  // Drag and drop event listeners
  ['dragenter', 'dragover'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const files = Array.from(e.dataTransfer.files);
    handleNewFiles(files);
  });

  dropzone.addEventListener('click', () => {
    fileInput.click();
  });

  dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener('change', () => {
    const files = Array.from(fileInput.files);
    handleNewFiles(files);
  });

  function handleNewFiles(files) {
    for (const f of files) {
      if (!supportedExtensions.some(ext => f.name.toLowerCase().endsWith(ext))) {
        showToast(`Skipped '${f.name}': Supported formats are PDF, JPG, JPEG, and PNG.`, 'warning');
        continue;
      }
      if (f.size > 50 * 1024 * 1024) {
        showToast(`Skipped '${f.name}': Exceeds 50MB limit.`, 'warning');
        continue;
      }
      if (!selectedFiles.some(existing => existing.name === f.name && existing.size === f.size)) {
        selectedFiles.push(f);
      }
    }
    renderFileList();
  }

  function renderFileList() {
    if (!fileList) return;
    fileList.replaceChildren();

    if (selectedFiles.length === 0) {
      if (uploadBtn) uploadBtn.disabled = true;
      if (uploadAndProcessBtn) uploadAndProcessBtn.disabled = true;
      return;
    }

    if (uploadBtn) uploadBtn.disabled = false;
    if (uploadAndProcessBtn) uploadAndProcessBtn.disabled = false;

    selectedFiles.forEach((file, idx) => {
      const item = document.createElement('div');
      item.className = 'list-group-item d-flex justify-content-between align-items-center';

      const fileInfo = document.createElement('div');
      const nameEl = document.createElement('strong');
      nameEl.textContent = file.name;
      const sizeEl = document.createElement('span');
      sizeEl.className = 'text-muted ms-2 small';
      sizeEl.textContent = `(${(file.size / 1024).toFixed(1)} KB)`;

      fileInfo.appendChild(nameEl);
      fileInfo.appendChild(sizeEl);

      const removeBtn = document.createElement('button');
      removeBtn.className = 'btn btn-sm btn-outline-danger';
      removeBtn.textContent = 'Remove';
      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        selectedFiles.splice(idx, 1);
        renderFileList();
      });

      item.appendChild(fileInfo);
      item.appendChild(removeBtn);
      fileList.appendChild(item);
    });
  }

  async function performUpload(shouldProcess = false) {
    if (selectedFiles.length === 0) return;

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('files', f));

    if (uploadBtn) uploadBtn.disabled = true;
    if (uploadAndProcessBtn) uploadAndProcessBtn.disabled = true;

    try {
      const res = await apiRequest('/api/statements/upload', {
        method: 'POST',
        body: formData,
      });

      const results = res.results || [];
      let successCount = 0;
      const failedIndexes = new Set();

      for (const [index, originalItem] of results.entries()) {
        let item = originalItem;
        if (item.error && item.error.code === 'PDF_PASSWORD_PROTECTED') {
          let retry = false;
          while (item.error && ['PDF_PASSWORD_PROTECTED', 'PDF_INVALID_PASSWORD'].includes(item.error.code)) {
            const password = await requestPdfPassword(item.filename, retry);
            if (password === null) {
              showToast(`${item.filename}: upload cancelled; enter the PDF password to continue.`, 'warning');
              break;
            }

            const retryForm = new FormData();
            retryForm.append('files', selectedFiles[index]);
            retryForm.append('password', password);
            const retryResult = await apiRequest('/api/statements/upload', {
              method: 'POST',
              body: retryForm,
            });
            item = (retryResult.results || [])[0] || item;
            retry = true;
          }
        }

        if (item.statement) {
          successCount++;
          if (shouldProcess) {
            try {
              await apiRequest(`/api/statements/${item.statement.id}/process`, {
                method: 'POST',
              });
            } catch (err) {
              showToast(
                `${item.filename}: uploaded, but processing could not be started: ${err.message}`,
                'danger',
              );
            }
          }
        } else if (item.error) {
          failedIndexes.add(index);
          if (item.error.code !== 'PDF_PASSWORD_PROTECTED') {
            showToast(`${item.filename}: ${item.error.code} - ${item.error.message}`, 'danger');
          }
        }
      }

      if (successCount > 0) {
        showToast(`Successfully uploaded ${successCount} statement(s).`, 'success');
        selectedFiles = selectedFiles.filter((file, index) => failedIndexes.has(index));
        renderFileList();
        onSuccess();
      }
    } catch (err) {
      // error handled in apiRequest
    } finally {
      if (uploadBtn) uploadBtn.disabled = selectedFiles.length === 0;
      if (uploadAndProcessBtn) uploadAndProcessBtn.disabled = selectedFiles.length === 0;
    }
  }

  if (uploadBtn) {
    uploadBtn.addEventListener('click', () => performUpload(false));
  }
  if (uploadAndProcessBtn) {
    uploadAndProcessBtn.addEventListener('click', () => performUpload(true));
  }
}
