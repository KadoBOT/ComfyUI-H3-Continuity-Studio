// Emit browser state for renderer agreement and saved-guide compatibility tests.
import { parseState, serialize } from '../../web/h3c_timeline_model.mjs?v=448aca934518';
import { splitBox } from '../../web/h3c_shot_split.mjs?v=b431e6b9a29c';
import { CONTEXT, shotGuideTimeline, savedGuideSplitTimeline, unstructuredGuideTimeline } from './shot_split_fixtures.mjs';

const shot = parseState(JSON.stringify(shotGuideTimeline()));
splitBox(shot, 0, 2, CONTEXT);
process.stdout.write(JSON.stringify({
  context: CONTEXT,
  shot: serialize(shot),
  saved: serialize(parseState(JSON.stringify(savedGuideSplitTimeline()))),
  unstructured: serialize(parseState(JSON.stringify(unstructuredGuideTimeline()))),
}));
