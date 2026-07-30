// task-06 Interfaces: `contentId` omitted/`undefined` => NEW mode (blank form, submitting
// creates and routes to the new item's page); a string id => EDIT mode (loads via
// `getContent`, prefills, submitting PATCHes).
export interface ContentEditorScreenProps {
  contentId?: string;
}
