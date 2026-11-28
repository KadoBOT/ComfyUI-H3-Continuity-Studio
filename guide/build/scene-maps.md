# Scene maps

A **scene map** is a top-down plan of a place, such as a floor plan, an aerial view or a sketch, with the camera and the characters placed on it. It tells H3 where the camera stands, which way it looks, and where each character starts and ends in a clip.

## Turn it on for a clip

In a clip's **Settings** tab, switch on **Scene map**. It is off by default; a clip without a map renders exactly as before. The section shows a small preview of the map and an **Edit map** button.

A project with a map switched on needs this version of H3 Continuity or later. Older versions open it read-only.

## Edit the map

**Edit map** opens the map in the centre of the Studio, titled **Scene map · Clip N**.

- **Map** chooses the plan from ComfyUI's input folder. **Upload…** adds one to `input/maps`.
- **Place camera**: press where the camera stands and drag towards where it looks. Select the camera arrow to set its **Field of view** and **Lens height**.
- **Add marker**: click the map for each character or object. Select a marker to give it a label, icon, colour and size, and to choose whether it appears in the legend.
- **Move** drags markers, the camera arrow or its aim ring. **Delete** removes the selection.

The **Opening** and **End** tabs hold where everything is at the start and at the end of the clip. The other tab is drawn faintly underneath, so you can see the move. A marker you don't move on **End** stays where it opened. The camera's lens, the labels and the legend are the same in both.

With a [Cast](../story/cast.md), a selected marker has a **Cast** picker. A linked marker is named in the prompt the way the clip names that character: its `<Subject N>` label when the clip prompt defines one, otherwise its Cast name.

## Continuing clips share the map

When a clip continues the previous one (no **Cut**) and you switch its map on, it starts where the previous clip's map ended, with the same picture, camera lens and markers. Its **Opening** tab reads **Shared with clip N's end**: dragging there moves the previous clip's **End**, because they are the same moment. Markers you add to the continuing clip belong to it.

To drop an inherited marker from a clip, select it and press **Not in this clip**. It is gone from that clip and the clips that continue it, and stays in the earlier ones. **Bring back** above the map restores it.

Turning on **Cut** for a clip ends the link. The clip keeps the positions it last showed, so nothing jumps. A map switched on after a cut starts from where the nearest earlier map on the same track ended.

## What the video gets

| Clip | Added to its prompt |
| --- | --- |
| The first clip, or one after a cut, without a **First frame**, rendering as T2VA or Ref2VA | The map in words, at the end of the `[Shot 1]` line of the description: where the camera stands, what is in frame and where, then how the camera and each character move from opening to end. |
| The same, with **Send map picture to video** on (Ref2VA only) | Also the map itself, drawn at 1 MP with the opening layout, as one more picture. A storyboard line in `subject_definitions` and a `weak_reference` line in `retention_analysis` tell H3 to follow the camera viewpoint and where each subject starts, without reproducing the plan's look. |
| A clip that continues the previous one, has a **First frame**, renders as FLF2VA, or has a map without a camera | Nothing. The section says why. |

A clip that already sends nine pictures cannot send the map picture; it still gets the words. The map describes the first shot only, so a clip with several shots says so. **Added to the prompt**, at the bottom of the section, shows the exact text for the video and for stills.

## What stills get

A pixel still recipe, such as [MiniMax H3 Image](minimax-h3-image-stills.md), receives the map as one more reference at 1 MP, with one line in the still prompt that describes the camera and says nothing from the plan is drawn. **First** and shot stills use the opening layout; a **Last** still uses the end. Other still recipes don't use the map.

## The H3 Scene Map node

In a graph, the **H3 Scene Map** node draws the same kind of map from a picture and outputs it with a line of text that describes it. Connect its image to a still generator's reference input to use it outside the Studio; the Studio introduces a connected map in the still prompt after the clip's own text.
