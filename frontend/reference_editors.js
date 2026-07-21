(() => {
  "use strict";

  let postJson = null;
  let getFileNameFromPath = null;
  let refreshUiFromHost = null;

  let rankingsEditorState = null;
  let rankingsEditorOpen = false;
  let rankingsEditorDragKey = "";
  let rankingsEditorDropAfter = false;
  let rankingsEditorAddCounter = 0;
  let rankingsEditorListScrollTop = 0;
  let referenceEditorState = null;
  let referenceEditorOpen = false;
  let referenceEditorAddCounter = 0;
  let referenceEditorListScrollTop = 0;

  const HIDDEN_SWIMMER_TYPE_NAME = "Non-Response / Unknown";

  function isHiddenReferenceEditorItem(item) {
    if (!referenceEditorState || referenceEditorState.purpose !== "swimmer_types") return false;
    const name = String(item?.fields?.swimmer_type_name ?? "").trim().toLowerCase();
    return name === HIDDEN_SWIMMER_TYPE_NAME.toLowerCase();
  }

  function getRankingsEditorElement(id) {
    return document.getElementById(id);
  }

  function setRankingsEditorError(message) {
    const error = getRankingsEditorElement("rankings-editor-error");
    if (!error) return;

    if (message) {
      error.textContent = message;
      error.classList.remove("hidden");
    } else {
      error.textContent = "";
      error.classList.add("hidden");
    }
  }

  function getRankingsEditorItems() {
    return rankingsEditorState?.swimmer_types?.[0]?.items ?? [];
  }

  function normalizeRankingsEditorItems(swimmerType) {
    swimmerType.items = (swimmerType.items ?? []).map((item, index) => ({
      ...item,
      rank: index + 1,
    }));
  }

  function openRankingsEditorModal() {
    const modal = getRankingsEditorElement("rankings-editor-modal");
    if (modal) modal.showModal();
    rankingsEditorOpen = true;
  }

  function closeRankingsEditor() {
    const modal = getRankingsEditorElement("rankings-editor-modal");
    const input = getRankingsEditorElement("rankings-editor-new-item-name");
    if (modal?.open) modal.close();
    if (input) input.value = "";
    setRankingsEditorError("");
    rankingsEditorOpen = false;
    rankingsEditorDragKey = "";
    rankingsEditorListScrollTop = 0;
    rankingsEditorState = null;
  }

  function moveRankingEditorItem(swimmerTypeId, draggedKey, targetKey, placeAfter) {
    if (!rankingsEditorState || !draggedKey || !targetKey || draggedKey === targetKey) return;

    const swimmerType = rankingsEditorState.swimmer_types.find((entry) => entry.id === swimmerTypeId);
    if (!swimmerType) return;

    const draggedIndex = swimmerType.items.findIndex((item) => item.client_key === draggedKey);
    const targetIndex = swimmerType.items.findIndex((item) => item.client_key === targetKey);
    if (draggedIndex < 0 || targetIndex < 0) return;

    const [draggedItem] = swimmerType.items.splice(draggedIndex, 1);
    let insertIndex = targetIndex;
    if (draggedIndex < targetIndex) insertIndex -= 1;
    if (placeAfter) insertIndex += 1;

    swimmerType.items.splice(insertIndex, 0, draggedItem);
    normalizeRankingsEditorItems(swimmerType);
  }

  function moveRankingsEditorItemByOffset(swimmerTypeId, clientKey, offset) {
    if (!rankingsEditorState || !offset) return;

    const swimmerType = rankingsEditorState.swimmer_types.find((entry) => entry.id === swimmerTypeId);
    if (!swimmerType) return;

    const currentIndex = swimmerType.items.findIndex((item) => item.client_key === clientKey);
    const nextIndex = currentIndex + offset;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= swimmerType.items.length) return;

    const [item] = swimmerType.items.splice(currentIndex, 1);
    swimmerType.items.splice(nextIndex, 0, item);
    normalizeRankingsEditorItems(swimmerType);
  }

  function deleteRankingsEditorItem(clientKey) {
    if (!rankingsEditorState || !clientKey) return;

    const totalItems = getRankingsEditorItems().length;
    if (totalItems <= 1) {
      setRankingsEditorError(`At least one ${rankingsEditorState.item_singular} must remain.`);
      return;
    }

    rankingsEditorState.swimmer_types.forEach((swimmerType) => {
      swimmerType.items = swimmerType.items.filter((item) => item.client_key !== clientKey);
      normalizeRankingsEditorItems(swimmerType);
    });

    setRankingsEditorError("");
    renderRankingsEditor();
  }

  function renderRankingsEditor() {
    if (!rankingsEditorState) return;

    const title = getRankingsEditorElement("rankings-editor-title");
    const subtitle = getRankingsEditorElement("rankings-editor-subtitle");
    const fileMeta = getRankingsEditorElement("rankings-editor-file-meta");
    const hint = getRankingsEditorElement("rankings-editor-hint");
    const picker = getRankingsEditorElement("rankings-editor-swimmer-type");
    const list = getRankingsEditorElement("rankings-editor-list");
    const input = getRankingsEditorElement("rankings-editor-new-item-name");

    const activeId = rankingsEditorState.activeSwimmerTypeId ?? rankingsEditorState.swimmer_types[0]?.id ?? null;
    rankingsEditorState.activeSwimmerTypeId = activeId;
    const swimmerType = rankingsEditorState.swimmer_types.find((entry) => entry.id === activeId) ?? rankingsEditorState.swimmer_types[0];
    if (!swimmerType || !picker || !list) return;

    const kindTitle = rankingsEditorState.kind === "color" ? "Color" : "Style";
    if (title) title.textContent = `Edit ${kindTitle} Rankings`;
    if (subtitle) subtitle.textContent = `Reorder ${rankingsEditorState.item_plural} for each swimmer type and save back to the selected files and rankings workbook.`;
    if (fileMeta) {
      const rankName = getFileNameFromPath(rankingsEditorState.rankings_path);
      const lookupName = getFileNameFromPath(rankingsEditorState.lookup_path);
      fileMeta.textContent = `${rankName} + ${lookupName}`;
    }
    if (hint) {
      hint.textContent = `Drag, use arrows, or delete items here. Adding a new ${rankingsEditorState.item_singular} inserts it at rank #1 for every swimmer type.`;
    }
    if (input) input.placeholder = `Add a new ${rankingsEditorState.item_singular}`;

    picker.innerHTML = "";
    rankingsEditorState.swimmer_types.forEach((entry) => {
      const option = document.createElement("option");
      option.value = String(entry.id);
      option.textContent = entry.name || `Swimmer Type ${entry.id}`;
      option.selected = entry.id === swimmerType.id;
      picker.append(option);
    });

    rankingsEditorListScrollTop = list.scrollTop;
    list.replaceChildren();
    swimmerType.items.forEach((item, index) => {
      const li = document.createElement("li");
      li.className = "rankings-editor-item";
      li.draggable = true;
      li.dataset.clientKey = item.client_key;

      li.addEventListener("dragstart", (event) => {
        rankingsEditorDragKey = item.client_key;
        li.classList.add("dragging");
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", item.client_key);
        }
      });

      li.addEventListener("dragend", () => {
        rankingsEditorDragKey = "";
        li.classList.remove("dragging");
        document.querySelectorAll(".rankings-editor-item.drag-over").forEach((node) => node.classList.remove("drag-over"));
      });

      li.addEventListener("dragover", (event) => {
        event.preventDefault();
        const rect = li.getBoundingClientRect();
        rankingsEditorDropAfter = event.clientY > rect.top + rect.height / 2;
        document.querySelectorAll(".rankings-editor-item.drag-over").forEach((node) => node.classList.remove("drag-over"));
        li.classList.add("drag-over");
      });

      li.addEventListener("dragleave", () => {
        li.classList.remove("drag-over");
      });

      li.addEventListener("drop", (event) => {
        event.preventDefault();
        li.classList.remove("drag-over");
        moveRankingEditorItem(swimmerType.id, rankingsEditorDragKey, item.client_key, rankingsEditorDropAfter);
        renderRankingsEditor();
      });

      const rank = document.createElement("span");
      rank.className = "rankings-editor-rank";
      rank.textContent = `#${index + 1}`;

      const body = document.createElement("div");
      body.className = "rankings-editor-item-body";

      const name = document.createElement("div");
      name.className = "rankings-editor-item-name";
      name.textContent = item.name;

      body.append(name);

      const handle = document.createElement("div");
      handle.className = "rankings-editor-drag-handle";
      handle.textContent = "::";

      const controls = document.createElement("div");
      controls.className = "rankings-editor-item-controls";

      const moveUp = document.createElement("button");
      moveUp.type = "button";
      moveUp.className = "rankings-editor-icon-button";
      moveUp.textContent = "\u2191";
      moveUp.title = "Move up";
      moveUp.disabled = index === 0;
      moveUp.addEventListener("click", (event) => {
        event.preventDefault();
        moveRankingsEditorItemByOffset(swimmerType.id, item.client_key, -1);
        renderRankingsEditor();
      });

      const moveDown = document.createElement("button");
      moveDown.type = "button";
      moveDown.className = "rankings-editor-icon-button";
      moveDown.textContent = "\u2193";
      moveDown.title = "Move down";
      moveDown.disabled = index === swimmerType.items.length - 1;
      moveDown.addEventListener("click", (event) => {
        event.preventDefault();
        moveRankingsEditorItemByOffset(swimmerType.id, item.client_key, 1);
        renderRankingsEditor();
      });

      controls.append(moveUp, moveDown, handle);

      li.append(rank, body);
      if (item.is_new) {
        const badge = document.createElement("span");
        badge.className = "rankings-editor-item-badge";
        badge.textContent = "New";
        li.append(badge);
      }
      li.append(controls);
      list.append(li);
    });

    list.scrollTop = rankingsEditorListScrollTop;

  }

  function addRankingsEditorItem() {
    if (!rankingsEditorState) return;

    const input = getRankingsEditorElement("rankings-editor-new-item-name");
    const newName = input?.value?.trim() ?? "";
    if (!newName) {
      setRankingsEditorError(`Enter a ${rankingsEditorState.item_singular} name first.`);
      return;
    }

    const existing = getRankingsEditorItems().some((item) => item.name.trim().toLowerCase() === newName.toLowerCase());
    if (existing) {
      setRankingsEditorError(`That ${rankingsEditorState.item_singular} already exists.`);
      return;
    }

    const clientKey = `new-${Date.now()}-${rankingsEditorAddCounter++}`;
    rankingsEditorState.swimmer_types.forEach((swimmerType) => {
      swimmerType.items.unshift({
        client_key: clientKey,
        id: null,
        name: newName,
        is_new: true,
        rank: 1,
      });
      normalizeRankingsEditorItems(swimmerType);
    });

    if (input) input.value = "";
    setRankingsEditorError("");
    renderRankingsEditor();
  }

  async function openRankingsEditor(purpose) {
    const output = document.getElementById("output");
    try {
      const data = await postJson("/api/rankings_editor/load", { purpose });
      rankingsEditorState = {
        ...data,
        activeSwimmerTypeId: data?.swimmer_types?.[0]?.id ?? null,
      };
      rankingsEditorState.swimmer_types.forEach(normalizeRankingsEditorItems);
      openRankingsEditorModal();
      renderRankingsEditor();
    } catch (e) {
      if (output) {
        output.textContent = `Rankings editor failed for "${purpose}".\n\n${String(e)}`;
      }
    }
  }

  async function saveRankingsEditor(refreshFn) {
    if (!rankingsEditorState) return;

    const saveButton = getRankingsEditorElement("rankings-editor-save");
    const output = document.getElementById("output");
    const items = getRankingsEditorItems().map((item) => ({
      client_key: item.client_key,
      id: item.id,
      name: item.name,
      is_new: Boolean(item.is_new),
    }));
    const swimmerTypes = rankingsEditorState.swimmer_types.map((swimmerType) => ({
      id: swimmerType.id,
      item_keys: swimmerType.items.map((item) => item.client_key),
    }));

    if (saveButton) saveButton.disabled = true;
    setRankingsEditorError("");

    try {
      const result = await postJson("/api/rankings_editor/save", {
        purpose: rankingsEditorState.purpose,
        items,
        swimmer_types: swimmerTypes,
      });
      if (output) {
        output.textContent =
          `Saved ${rankingsEditorState.item_plural} for ${getFileNameFromPath(rankingsEditorState.rankings_path)}.\n` +
          `New items were also written to ${getFileNameFromPath(rankingsEditorState.lookup_path)} when needed.` +
          (result?.workbook_synced
            ? `\nUpdated workbook: ${getFileNameFromPath(result.workbook_path)}`
            : (result?.workbook_warning ? `\nWorkbook warning: ${result.workbook_warning}` : ""));
      }
      closeRankingsEditor();
      await refreshFn();
    } catch (e) {
      setRankingsEditorError(String(e));
    } finally {
      if (saveButton) saveButton.disabled = false;
    }
  }

  function getReferenceEditorElement(id) {
    return document.getElementById(id);
  }

  function setReferenceEditorError(message) {
    const error = getReferenceEditorElement("reference-editor-error");
    if (!error) return;

    if (message) {
      error.textContent = message;
      error.classList.remove("hidden");
    } else {
      error.textContent = "";
      error.classList.add("hidden");
    }
  }

  function setReferenceEditorFormError(message) {
    const error = getReferenceEditorElement("reference-editor-form-error");
    if (!error) return;

    if (message) {
      error.textContent = message;
      error.classList.remove("hidden");
    } else {
      error.textContent = "";
      error.classList.add("hidden");
    }
  }

  function normalizeReferenceEditorItem(item, fieldColumns = referenceEditorState?.field_columns ?? []) {
    const fields = {};
    fieldColumns.forEach((fieldName) => {
      fields[fieldName] = String(item?.fields?.[fieldName] ?? "").trim();
    });

    return {
      client_key: item?.client_key ?? `new-${Date.now()}-${referenceEditorAddCounter++}`,
      id: item?.id ?? null,
      fields,
    };
  }

  function createEmptyReferenceEditorFields() {
    const fields = {};
    (referenceEditorState?.field_columns ?? []).forEach((fieldName) => {
      fields[fieldName] = "";
    });
    return fields;
  }

  function getReferenceEditorTitleValue(fields) {
    if (!referenceEditorState) return "";
    return String(fields?.[referenceEditorState.title_field] ?? "").trim();
  }

  function openReferenceEditorModal() {
    const modal = getReferenceEditorElement("reference-editor-modal");
    if (modal) modal.showModal();
    referenceEditorOpen = true;
  }

  function closeReferenceEditor() {
    const modal = getReferenceEditorElement("reference-editor-modal");
    if (modal?.open) modal.close();
    closeReferenceEditorForm(false);
    setReferenceEditorError("");
    setReferenceEditorFormError("");
    referenceEditorOpen = false;
    referenceEditorListScrollTop = 0;
    referenceEditorState = null;
  }

  function openReferenceEditorForm(mode, clientKey = null) {
    if (!referenceEditorState) return;

    const currentItem = clientKey
      ? referenceEditorState.items.find((item) => item.client_key === clientKey)
      : null;

    referenceEditorState.formMode = mode;
    referenceEditorState.editingClientKey = clientKey;
    referenceEditorState.formDraft = currentItem
      ? { ...currentItem.fields }
      : createEmptyReferenceEditorFields();

    setReferenceEditorError("");
    setReferenceEditorFormError("");
    renderReferenceEditorForm();
  }

  function closeReferenceEditorForm(shouldRender = true) {
    const modal = getReferenceEditorElement("reference-editor-form-modal");
    if (modal?.open) modal.close();

    if (!referenceEditorState) return;
    referenceEditorState.formMode = null;
    referenceEditorState.editingClientKey = null;
    referenceEditorState.formDraft = null;
    setReferenceEditorError("");
    setReferenceEditorFormError("");
    if (shouldRender) renderReferenceEditor();
  }

  function updateReferenceEditorDraftField(fieldName, value) {
    if (!referenceEditorState?.formDraft) return;
    referenceEditorState.formDraft[fieldName] = value;
  }

  function getReferenceEditorFieldLabel(fieldName) {
    const labels = {
      color_name: "Color name",
      traits: "Traits",
      style_code: "Style code",
      style_name: "Style name",
      expertise_area: "Expertise area",
      swimmer_type_name: "Swimmer type name",
    };

    return labels[fieldName] || fieldName.replaceAll("_", " ");
  }

  function getReferenceEditorFieldPlaceholder(fieldName) {
    const placeholders = {
      color_name: "Color name e.g Blue",
      traits: "Traits e.g Knowledgeable, Experienced",
      style_code: "Style code e.g DIA",
      style_name: "Style name e.g Do-It-Alls",
      expertise_area: "Expertise area e.g Anything!",
      swimmer_type_name: "Swimmer type name e.g The Natural",
    };

    return placeholders[fieldName] || getReferenceEditorFieldLabel(fieldName);
  }

  function deleteReferenceEditorItem(clientKey) {
    if (!referenceEditorState || !clientKey) return;

    referenceEditorState.items = referenceEditorState.items.filter((item) => item.client_key !== clientKey);
    setReferenceEditorError("");
    renderReferenceEditor();
  }

  function getReferenceEditorFieldDescription(item) {
    if (!referenceEditorState) return "";

    const lines = [];
    referenceEditorState.field_columns.forEach((fieldName) => {
      if (fieldName === referenceEditorState.title_field) return;
      const value = String(item.fields?.[fieldName] ?? "").trim();
      if (!value) return;
      lines.push(`${getReferenceEditorFieldLabel(fieldName)}: ${value}`);
    });

    return lines.join(" | ");
  }

  function renderReferenceEditorForm() {
    const formPanel = getReferenceEditorElement("reference-editor-form-modal");
    const formTitle = getReferenceEditorElement("reference-editor-form-title");
    const formFields = getReferenceEditorElement("reference-editor-form-fields");
    if (!formPanel || !formTitle || !formFields || !referenceEditorState) return;

    const isVisible = Boolean(referenceEditorState.formMode && referenceEditorState.formDraft);
    formFields.replaceChildren();
    if (isVisible && !formPanel.open) formPanel.showModal();
    else if (!isVisible && formPanel.open) formPanel.close();
    if (!isVisible) {
      setReferenceEditorFormError("");
      return;
    }

    formTitle.textContent = `${referenceEditorState.formMode === "edit" ? "Edit" : "Add"} ${referenceEditorState.item_singular}`;
    setReferenceEditorFormError("");

    referenceEditorState.field_columns.forEach((fieldName) => {
      const wrapper = document.createElement("label");
      wrapper.className = "reference-editor-field";

      const label = document.createElement("span");
      label.textContent = getReferenceEditorFieldLabel(fieldName);

      const field = fieldName === "traits"
        ? document.createElement("textarea")
        : document.createElement("input");
      field.value = referenceEditorState.formDraft?.[fieldName] ?? "";
      field.placeholder = getReferenceEditorFieldPlaceholder(fieldName);
      field.addEventListener("input", () => {
        updateReferenceEditorDraftField(fieldName, field.value);
      });

      wrapper.append(label, field);
      formFields.append(wrapper);
    });
  }

  function renderReferenceEditor() {
    if (!referenceEditorState) return;

    const title = getReferenceEditorElement("reference-editor-title");
    const subtitle = getReferenceEditorElement("reference-editor-subtitle");
    const fileMeta = getReferenceEditorElement("reference-editor-file-meta");
    const addButton = getReferenceEditorElement("reference-editor-add-button");
    const list = getReferenceEditorElement("reference-editor-list");
    if (!list) return;

    const titleMap = {
      personality_colors: "Edit Personality Colors",
      instructor_styles: "Edit Instructor Styles",
      swimmer_types: "Edit Swimmer Types",
    };

    if (title) title.textContent = titleMap[referenceEditorState.purpose] || "Edit Reference Table";
    if (subtitle) {
      subtitle.textContent = `Review existing ${referenceEditorState.item_plural}, add new ones, and save changes back to the selected CSV files and rankings workbook.`;
    }
    if (fileMeta) fileMeta.textContent = getFileNameFromPath(referenceEditorState.path);
    if (addButton) addButton.textContent = `Add ${referenceEditorState.item_singular}`;

    referenceEditorListScrollTop = list.scrollTop;
    list.replaceChildren();
    const visibleItems = referenceEditorState.items.filter((item) => !isHiddenReferenceEditorItem(item));

    visibleItems.forEach((item) => {
      const li = document.createElement("li");
      li.className = "rankings-editor-item reference-editor-item";

      const body = document.createElement("div");
      body.className = "rankings-editor-item-body";

      const titleValue = getReferenceEditorTitleValue(item.fields);

      const name = document.createElement("div");
      name.className = "rankings-editor-item-name";
      name.textContent = titleValue || `${referenceEditorState.item_singular} ${item.id ?? "new"}`;

      const meta = document.createElement("div");
      meta.className = "reference-editor-row-meta";
      meta.textContent = getReferenceEditorFieldDescription(item);
      meta.classList.toggle("hidden", !meta.textContent);

      body.append(name, meta);

      const controls = document.createElement("div");
      controls.className = "rankings-editor-item-controls";

      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.className = "rankings-editor-icon-button";
      editButton.textContent = "\u270E";
      editButton.title = `Edit ${titleValue || referenceEditorState.item_singular}`;
      editButton.addEventListener("click", (event) => {
        event.preventDefault();
        openReferenceEditorForm("edit", item.client_key);
      });

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "rankings-editor-icon-button danger";
      removeButton.textContent = "\u00D7";
      removeButton.title = `Delete ${titleValue || referenceEditorState.item_singular}`;
      removeButton.addEventListener("click", (event) => {
        event.preventDefault();
        deleteReferenceEditorItem(item.client_key);
      });

      controls.append(editButton, removeButton);
      li.append(body, controls);
      list.append(li);
    });

    list.scrollTop = referenceEditorListScrollTop;
    renderReferenceEditorForm();
  }

  function applyReferenceEditorFormChanges() {
    if (!referenceEditorState?.formDraft) return;

    const normalizedFields = {};
    referenceEditorState.field_columns.forEach((fieldName) => {
      normalizedFields[fieldName] = String(referenceEditorState.formDraft?.[fieldName] ?? "").trim();
    });

    const titleValue = getReferenceEditorTitleValue(normalizedFields);
    if (!titleValue) {
      setReferenceEditorFormError(`Enter a ${referenceEditorState.item_singular} name first.`);
      return;
    }

    const editingClientKey = referenceEditorState.editingClientKey;
    const duplicate = referenceEditorState.items.some((item) => {
      if (editingClientKey && item.client_key === editingClientKey) return false;
      return getReferenceEditorTitleValue(item.fields).toLowerCase() === titleValue.toLowerCase();
    });
    if (duplicate) {
      setReferenceEditorFormError(`That ${referenceEditorState.item_singular} already exists.`);
      return;
    }

    if (referenceEditorState.formMode === "edit" && editingClientKey) {
      const currentItem = referenceEditorState.items.find((item) => item.client_key === editingClientKey);
      if (!currentItem) {
        setReferenceEditorFormError(`Could not find that ${referenceEditorState.item_singular}.`);
        return;
      }
      currentItem.fields = normalizedFields;
    } else {
      referenceEditorState.items.unshift(normalizeReferenceEditorItem({
        client_key: `new-${Date.now()}-${referenceEditorAddCounter++}`,
        id: null,
        fields: normalizedFields,
      }));
    }

    setReferenceEditorFormError("");
    closeReferenceEditorForm();
  }

  async function openReferenceEditor(purpose) {
    const output = document.getElementById("output");
    try {
      const data = await postJson("/api/reference_table/load", { purpose });
      referenceEditorState = {
        ...data,
        items: (data?.items ?? []).map((item) => normalizeReferenceEditorItem(item, data?.field_columns ?? [])),
        formMode: null,
        editingClientKey: null,
        formDraft: null,
      };
      openReferenceEditorModal();
      renderReferenceEditor();
    } catch (e) {
      if (output) {
        output.textContent = `Reference editor failed for "${purpose}".\n\n${String(e)}`;
      }
    }
  }

  async function saveReferenceEditor(refreshFn) {
    if (!referenceEditorState) return;
    if (referenceEditorState.formDraft) {
      setReferenceEditorError("Apply or cancel the current form changes first.");
      return;
    }

    const saveButton = getReferenceEditorElement("reference-editor-save");
    const output = document.getElementById("output");
    if (saveButton) saveButton.disabled = true;
    setReferenceEditorError("");

    try {
      const result = await postJson("/api/reference_table/save", {
        purpose: referenceEditorState.purpose,
        items: referenceEditorState.items.map((item) => ({
          client_key: item.client_key,
          id: item.id,
          fields: item.fields,
        })),
      });

      if (output) {
        output.textContent =
          `Saved ${referenceEditorState.item_plural} to ${getFileNameFromPath(referenceEditorState.path)}.` +
          (result?.workbook_synced
            ? "\nUpdated rankings workbook."
            : (result?.workbook_warning ? `\nWorkbook warning: ${result.workbook_warning}` : ""));
      }

      closeReferenceEditor();
      await refreshFn();
    } catch (e) {
      setReferenceEditorError(String(e));
    } finally {
      if (saveButton) saveButton.disabled = false;
    }
  }

  function getRequiredElement(id) {
    const element = document.getElementById(id);
    if (!element) throw new Error(`Missing element with id="${id}"`);
    return element;
  }

  function wireReferenceEditors({ postJson: injectedPostJson, getFileNameFromPath: injectedGetFileNameFromPath, refreshUi }) {
    postJson = injectedPostJson;
    getFileNameFromPath = injectedGetFileNameFromPath;
    refreshUiFromHost = refreshUi;

    getRequiredElement("swimmerTypeColorRankingsEditButton").addEventListener("click", async () => {
      await openRankingsEditor("swimmer_type_color_rankings");
    });
    getRequiredElement("swimmerTypeStyleRankingsEditButton").addEventListener("click", async () => {
      await openRankingsEditor("swimmer_type_style_rankings");
    });
    getRequiredElement("personalityColorsManageButton").addEventListener("click", async () => {
      await openReferenceEditor("personality_colors");
    });
    getRequiredElement("instructorStylesManageButton").addEventListener("click", async () => {
      await openReferenceEditor("instructor_styles");
    });
    getRequiredElement("swimmerTypesManageButton").addEventListener("click", async () => {
      await openReferenceEditor("swimmer_types");
    });

    const rankingsEditorClose = document.getElementById("rankings-editor-close");
    const rankingsEditorCancel = document.getElementById("rankings-editor-cancel");
    const rankingsEditorSave = document.getElementById("rankings-editor-save");
    const rankingsEditorAdd = document.getElementById("rankings-editor-add-button");
    const rankingsEditorPicker = document.getElementById("rankings-editor-swimmer-type");
    const rankingsEditorInput = document.getElementById("rankings-editor-new-item-name");
    const rankingsEditorList = document.getElementById("rankings-editor-list");
    const referenceEditorClose = document.getElementById("reference-editor-close");
    const referenceEditorCancel = document.getElementById("reference-editor-cancel");
    const referenceEditorSave = document.getElementById("reference-editor-save");
    const referenceEditorAdd = document.getElementById("reference-editor-add-button");
    const referenceEditorFormClose = document.getElementById("reference-editor-form-close");
    const referenceEditorFormCancel = document.getElementById("reference-editor-form-cancel");
    const referenceEditorApply = document.getElementById("reference-editor-apply-button");
    const rankingsEditorDialog = document.getElementById("rankings-editor-modal");
    const referenceEditorDialog = document.getElementById("reference-editor-modal");
    const referenceEditorFormDialog = document.getElementById("reference-editor-form-modal");

    if (rankingsEditorDialog) {
      rankingsEditorDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeRankingsEditor(); });
    }
    if (referenceEditorDialog) {
      referenceEditorDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeReferenceEditor(); });
    }
    if (referenceEditorFormDialog) {
      referenceEditorFormDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeReferenceEditorForm(); });
    }
    if (rankingsEditorClose) rankingsEditorClose.addEventListener("click", closeRankingsEditor);
    if (rankingsEditorCancel) rankingsEditorCancel.addEventListener("click", closeRankingsEditor);
    if (rankingsEditorSave) rankingsEditorSave.addEventListener("click", async () => {
      await saveRankingsEditor(refreshUiFromHost);
    });
    if (rankingsEditorAdd) rankingsEditorAdd.addEventListener("click", addRankingsEditorItem);
    if (rankingsEditorPicker) {
      rankingsEditorPicker.addEventListener("change", () => {
        if (!rankingsEditorState) return;
        rankingsEditorState.activeSwimmerTypeId = Number(rankingsEditorPicker.value);
        setRankingsEditorError("");
        renderRankingsEditor();
      });
    }
    if (rankingsEditorInput) {
      rankingsEditorInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          addRankingsEditorItem();
        }
      });
    }
    if (rankingsEditorList) {
      rankingsEditorList.addEventListener("dragover", (event) => {
        event.preventDefault();
      });
      rankingsEditorList.addEventListener("drop", (event) => {
        if (!rankingsEditorState || event.target !== rankingsEditorList) return;
        event.preventDefault();
        const swimmerType = rankingsEditorState.swimmer_types.find((entry) => entry.id === rankingsEditorState.activeSwimmerTypeId);
        const lastKey = swimmerType?.items?.[swimmerType.items.length - 1]?.client_key;
        if (!lastKey) return;
        moveRankingEditorItem(swimmerType.id, rankingsEditorDragKey, lastKey, true);
        renderRankingsEditor();
      });
    }
    if (referenceEditorClose) referenceEditorClose.addEventListener("click", closeReferenceEditor);
    if (referenceEditorCancel) referenceEditorCancel.addEventListener("click", closeReferenceEditor);
    if (referenceEditorSave) {
      referenceEditorSave.addEventListener("click", async () => {
        await saveReferenceEditor(refreshUiFromHost);
      });
    }
    if (referenceEditorAdd) {
      referenceEditorAdd.addEventListener("click", () => {
        openReferenceEditorForm("add");
      });
    }
    if (referenceEditorFormClose) {
      referenceEditorFormClose.addEventListener("click", () => closeReferenceEditorForm());
    }
    if (referenceEditorFormCancel) {
      referenceEditorFormCancel.addEventListener("click", closeReferenceEditorForm);
    }
    if (referenceEditorApply) {
      referenceEditorApply.addEventListener("click", applyReferenceEditorFormChanges);
    }
  }

  window.AquaReferenceEditors = Object.freeze({ wireReferenceEditors });
})();
