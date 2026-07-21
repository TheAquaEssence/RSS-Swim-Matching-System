"use strict";

const DIALOG_CHANNELS = Object.freeze({
  OPEN_INPUT_FILE: "aqua:dialog:open-input-file",
});

const TABULAR_EXTENSIONS = Object.freeze(["csv", "xlsx", "xlsm"]);
const CSV_EXTENSIONS = Object.freeze(["csv"]);

const INPUT_FILE_PURPOSES = Object.freeze({
  classes: Object.freeze({ title: "Select classes data", extensions: TABULAR_EXTENSIONS }),
  swimmers: Object.freeze({ title: "Select swimmers data", extensions: TABULAR_EXTENSIONS }),
  instructors: Object.freeze({ title: "Select instructors data", extensions: TABULAR_EXTENSIONS }),
  swimmer_type_color_rankings: Object.freeze({
    title: "Select swimmer type color rankings",
    extensions: CSV_EXTENSIONS,
  }),
  swimmer_type_style_rankings: Object.freeze({
    title: "Select swimmer type style rankings",
    extensions: CSV_EXTENSIONS,
  }),
  personality_colors: Object.freeze({ title: "Select personality colors", extensions: CSV_EXTENSIONS }),
  instructor_styles: Object.freeze({ title: "Select instructor styles", extensions: CSV_EXTENSIONS }),
  swimmer_types: Object.freeze({ title: "Select swimmer types", extensions: CSV_EXTENSIONS }),
});

module.exports = Object.freeze({
  DIALOG_CHANNELS,
  INPUT_FILE_PURPOSES,
});
