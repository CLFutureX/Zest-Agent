from sdk.utils.chain import ChainContext, FunctionStep, chain





def build_conversation_query_chain():

    def _capture_input(conversation_id: str, context: ChainContext) -> str:

        context.set("conversation_id", conversation_id)

        return conversation_id



    def _load_state(conversation_id: str, context: ChainContext) -> dict[str, object]:

        return {

            "conversation_id": conversation_id,

            "has_state": context.get("has_state", False),

        }



    def _load_related_parts(state_payload: dict[str, object], context: ChainContext) -> dict[str, object]:

        return {

            "state": state_payload,

            "events": context.get("events", []),

            "memories": context.get("memories", []),

        }



    def _build_view(payload: dict[str, object], context: ChainContext) -> dict[str, object]:

        return {

            "conversation_id": context.get("conversation_id"),

            "state": payload["state"],

            "events": payload["events"],

            "memories": payload["memories"],

        }



    return (

        chain(FunctionStep(_capture_input, name="capture_input"))

        .then(FunctionStep(_load_state, name="load_state"))

        .branch(

            lambda payload, _context: bool(payload.get("has_state")),

            if_true=chain(FunctionStep(_load_related_parts, name="load_related_parts")),

            if_false=chain(FunctionStep(lambda payload, _context: {"state": payload, "events": [], "memories": []}, name="empty_related_parts")),

            name="has_state_branch",

        )

        .then(FunctionStep(_build_view, name="build_view"))

    )
