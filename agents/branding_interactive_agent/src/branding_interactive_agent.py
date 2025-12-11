###### Parsers, Formats, Utils
import argparse
import logging
import json
import pydash

###### Blue
from blue.agent import Agent, AgentFactory
from blue.session import Session
from blue.stream import ControlCode, Message

###### HELPER func import 
import util_functions  # e.g. load_service_description, generate_brand_identity, save_brand_identity

# set log level
logging.getLogger().setLevel(logging.INFO)
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] [%(process)d:%(threadName)s:%(thread)d](%(filename)s:%(lineno)d) %(name)s -  %(message)s",
    level=logging.ERROR,
    datefmt="%Y-%m-%d %H:%M:%S",
)
# ---- welcome arg
WELCOME_TEXT = (
    "Hi, welcome to IdeAction, your personal branding and marketing assistant. ✨\n\n"
    "First, let’s set up your profile so I can personalize your brand and marketing plan."
)

############################
### Agent.BrandingInteractiveAgent
#
class BrandingInteractiveAgent(Agent):
    """
    Interactive branding workshop agent.

    Flow:
      - On first EOS (no branding.step yet), show Step 1 form.
      - On each EVENT with action = "DONE", advance step:
        1) service_summary
        2) brand_core_message
        3) values_and_tone_raw
        4) audience_raw
        5) visuals_raw -> synthesize BrandIdentityMap and save.
    """

    def __init__(self, **kwargs):
        if "name" not in kwargs:
            kwargs["name"] = "BRANDING_INTERACTIVE"
        super().__init__(**kwargs)

    # ------------- Helpers for steps & state -------------

    def _get_step(self, worker):
        step = worker.get_data("branding.step")
        if step is None:
            step = 0
        return step

    def _set_step(self, worker, step):
        worker.set_data("branding.step", step)

    def _get_state(self, worker):
        state = worker.get_data("branding.state")
        if state is None:
            state = {}
        return state

    def _set_state(self, worker, state):
        worker.set_data("branding.state", state)

    # ------------- initial input form builder -------------

    def _create_profile_form(self, worker):
        
        # Step 0: collect basic user profile -> app_user (full_name, locale)
        
        args = {
            "schema": {
                "type": "object",
                "properties": {
                    "full_name": {
                        "type": "string",
                        "title": "What is your name?",
                    },
                    "locale": {
                        "type": "string",
                        "title": "Preferred language / region (optional)",
                    },
                },
                "required": ["full_name"],
            },
            "uischema": {
                "type": "VerticalLayout",
                "elements": [
                    {
                        "type": "Label",
                        "label": "Let’s start with your profile.",
                        "props": {
                            "large": True,
                            "style": {"marginBottom": 15, "fontSize": "15pt"},
                        },
                    },
                    {
                        "type": "Label",
                        "label": (
                            "I’ll use this to personalize your brand and content. "
                            "You can always update it later."
                        ),
                    },
                    {
                        "type": "Control",
                        "label": "Your name",
                        "scope": "#/properties/full_name",
                    },
                    {
                        "type": "Control",
                        "label": "Preferred language / region (e.g. en-US, es-MX)",
                        "scope": "#/properties/locale",
                    },
                    {
                        "type": "Button",
                        "label": "Save my profile",
                        "props": {
                            "intent": "success",
                            "action": "DONE",
                            "large": True,
                        },
                    },
                ],
            },
        }
        worker.write_control(ControlCode.CREATE_FORM, args, output="FORM")


    # ------------- Form builders -------------

    def _create_step1_form(self, worker):
        """
        Step 1: basic service summary
        """
        args = {
            "schema": {
                "type": "object",
                "properties": {
                    "service_summary": {"type": "string"},
                },
                "required": ["service_summary"],
            },
            "uischema": {
                "type": "VerticalLayout",
                "elements": [
                    {
                        "type": "Label",
                        "label": "Let’s start with the basics.",
                        "props": {
                            "large": True,
                            "style": {"marginBottom": 15, "fontSize": "15pt"},
                        },
                    },
                    {
                        "type": "Label",
                        "label": "In 1–2 sentences, what do you do or offer?",
                    },
                    {
                        "type": "Control",
                        "label": "Your service or business",
                        "scope": "#/properties/service_summary",
                    },
                    {
                        "type": "Button",
                        "label": "Next",
                        "props": {
                            "intent": "success",
                            "action": "DONE",
                            "large": True,
                        },
                    },
                ],
            },
        }
        worker.write_control(ControlCode.CREATE_FORM, args, output="FORM")

    def _create_step2_form(self, worker):
        """
        Step 2: brand core message
        """
        args = {
            "schema": {
                "type": "object",
                "properties": {
                    "brand_core_message": {"type": "string"},
                },
                "required": ["brand_core_message"],
            },
            "uischema": {
                "type": "VerticalLayout",
                "elements": [
                    {
                        "type": "Label",
                        "label": "What do you want people to remember about your brand in one sentence?",
                        "props": {
                            "large": True,
                            "style": {"marginBottom": 15, "fontSize": "15pt"},
                        },
                    },
                    {
                        "type": "Control",
                        "label": "Core brand message",
                        "scope": "#/properties/brand_core_message",
                    },
                    {
                        "type": "Button",
                        "label": "Next",
                        "props": {
                            "intent": "success",
                            "action": "DONE",
                            "large": True,
                        },
                    },
                ],
            },
        }
        worker.write_control(ControlCode.CREATE_FORM, args, output="FORM")

    def _create_step3_form(self, worker):
        """
        Step 3: values & tone (free-form answer for now)
        """
        args = {
            "schema": {
                "type": "object",
                "properties": {
                    "values_and_tone_raw": {"type": "string"},
                },
                "required": ["values_and_tone_raw"],
            },
            "uischema": {
                "type": "VerticalLayout",
                "elements": [
                    {
                        "type": "Label",
                        "label": "Values & tone",
                        "props": {
                            "large": True,
                            "style": {"marginBottom": 15, "fontSize": "15pt"},
                        },
                    },
                    {
                        "type": "Label",
                        "label": (
                            "1) List 3–7 core values for your brand (comma-separated).\n"
                            "2) Describe how your brand should sound (e.g., warm, expert, playful).\n"
                            "You can answer both in one message."
                        ),
                    },
                    {
                        "type": "Control",
                        "label": "Values & tone",
                        "scope": "#/properties/values_and_tone_raw",
                    },
                    {
                        "type": "Button",
                        "label": "Next",
                        "props": {
                            "intent": "success",
                            "action": "DONE",
                            "large": True,
                        },
                    },
                ],
            },
        }
        worker.write_control(ControlCode.CREATE_FORM, args, output="FORM")

    def _create_step4_form(self, worker):
        """
        Step 4: audience / personas
        """
        args = {
            "schema": {
                "type": "object",
                "properties": {
                    "audience_raw": {"type": "string"},
                },
                "required": ["audience_raw"],
            },
            "uischema": {
                "type": "VerticalLayout",
                "elements": [
                    {
                        "type": "Label",
                        "label": "Who is your ideal client?",
                        "props": {
                            "large": True,
                            "style": {"marginBottom": 15, "fontSize": "15pt"},
                        },
                    },
                    {
                        "type": "Label",
                        "label": (
                            "Describe them in 1–3 sentences, including their goals and frustrations."
                        ),
                    },
                    {
                        "type": "Control",
                        "label": "Ideal client description",
                        "scope": "#/properties/audience_raw",
                    },
                    {
                        "type": "Button",
                        "label": "Next",
                        "props": {
                            "intent": "success",
                            "action": "DONE",
                            "large": True,
                        },
                    },
                ],
            },
        }
        worker.write_control(ControlCode.CREATE_FORM, args, output="FORM")

    def _create_step5_form(self, worker):
        """
        Step 5: visual direction
        """
        args = {
            "schema": {
                "type": "object",
                "properties": {
                    "visuals_raw": {"type": "string"},
                },
                "required": ["visuals_raw"],
            },
            "uischema": {
                "type": "VerticalLayout",
                "elements": [
                    {
                        "type": "Label",
                        "label": "Visual direction",
                        "props": {
                            "large": True,
                            "style": {"marginBottom": 15, "fontSize": "15pt"},
                        },
                    },
                    {
                        "type": "Label",
                        "label": (
                            "What colors, styles, or vibes do you imagine for your brand?\n"
                            "Any brands or aesthetics you like (even outside your industry)?"
                        ),
                    },
                    {
                        "type": "Control",
                        "label": "Visuals & inspiration",
                        "scope": "#/properties/visuals_raw",
                    },
                    {
                        "type": "Button",
                        "label": "Finish",
                        "props": {
                            "intent": "success",
                            "action": "DONE",
                            "large": True,
                        },
                    },
                ],
            },
        }
        worker.write_control(ControlCode.CREATE_FORM, args, output="FORM")

    # ---------- Main processor -------------

    def default_processor(self, message, input="DEFAULT", properties=None, worker=None):
        stream = message.getStream()

        if not worker:
            worker = self.create_worker(None)

        # Handle UI events from forms
        if input == "EVENT":
            # Safely fetch event data up-front so `data`/`action` are always defined
            data = message.getData()
            form_id = None
            action = None
            if message.isData() and data:
                form_id = data.get("form_id")
                action = data.get("action")

                if action == "DONE":
                    # Close the current form
                    if form_id:
                        worker.write_control(
                            ControlCode.CLOSE_FORM,
                            {"form_id": form_id},
                            output="FORM",
                        )

                    step = self._get_step(worker)
                    state = self._get_state(worker)

    # STEP 0: user profile -> app_user
                    if step == 0:
                        full_name_data = worker.get_data("full_name.value") or {}
                        locale_data = worker.get_data("locale.value") or {}

                        full_name = (full_name_data.get("value") or "").strip()
                        locale = (locale_data.get("value") or "").strip() or None

                        if not full_name:
                            # Simple validation: ask again if empty
                            worker.write_data(
                                "I need at least a name so I know how to address you. 😊",
                                output="TEXT",
                            )
                            # Re-open the profile form
                            self._create_profile_form(worker)
                            return None

                        # Save to DB via util_functions (you implement this helper)
                        try:
                            app_user_id = util_functions.save_app_user(
                                full_name=full_name,
                                locale=locale,
                            )
                        except Exception as e:
                            logging.error(f"Error saving app_user: {e}")
                            worker.write_data(
                                "I had trouble saving your profile. Please try again in a moment.",
                                output="TEXT",
                            )
                            # Re-open the profile form so they can retry
                            self._create_profile_form(worker)
                            return None

                        # Store in state for later steps/agents if needed
                        state["app_user_id"] = str(app_user_id)
                        state["full_name"] = full_name
                        state["locale"] = locale
                        self._set_state(worker, state)

                        # Friendly confirmation
                        worker.write_data(
                            f"Nice to meet you, {full_name}! 🎉 Your profile is saved.\n\n"
                            "Next, let’s start mapping your brand identity.",
                            output="TEXT",
                        )

                        self._set_step(worker, 1)
                        self._create_step1_form(worker)

        # STEP 1: service summary
                    elif step == 1:
                        service_summary_data = worker.get_data("service_summary.value") or {}
                        service_summary = (service_summary_data.get("value") or "").strip()

                        if not service_summary:
                            worker.write_data(
                                "Give me 1–2 sentences about what you do or offer so I can ground your brand identity. 🙂",
                                output="TEXT",
                            )
                            self._create_step1_form(worker)
                            return None

                        state["service_summary"] = service_summary
                        self._set_state(worker, state)

                        # (Optionally: create project + service_description here, see below.)
                        # self._maybe_create_project(worker, state)

                        self._set_step(worker, 2)
                        self._create_step2_form(worker)

        # STEP 2: brand core message
                    elif step == 2:
                        core_msg = worker.get_data("brand_core_message.value")
                        state["brand_core_message"] = core_msg
                        self._set_state(worker, state)

                        self._set_step(worker, 3)
                        self._create_step3_form(worker)

        # STEP 3: values & tone
                    elif step == 3:
                        values_and_tone = worker.get_data("values_and_tone_raw.value")
                        state["values_and_tone_raw"] = values_and_tone
                        self._set_state(worker, state)

                        self._set_step(worker, 4)
                        self._create_step4_form(worker)

        # STEP 4: audience
                    elif step == 4:
                        audience_raw = worker.get_data("audience_raw.value")
                        state["audience_raw"] = audience_raw
                        self._set_state(worker, state)

                        self._set_step(worker, 5)
                        self._create_step5_form(worker)

        # STEP 5: visuals -> finalize
                    elif step == 5:
                        visuals_raw = worker.get_data("visuals_raw.value")
                        state["visuals_raw"] = visuals_raw
                        self._set_state(worker, state)

                        # At this point all answers are in `state`
                        # Optional: get project_id from properties 
                        project_id = None
                        if properties and "project_id" in properties:
                            project_id = properties["project_id"]
                        else:
                            project_id = self.properties.get("project_id")

                        # Load service description if you want to pass it into LLM
                        service_desc = None
                        try:
                            if project_id:
                                service_desc = util_functions.load_service_description(project_id)
                        except Exception as e:
                            logging.error(f"Error loading service description: {e}")

                        # 1) Generate BrandIdentityMap using your LLM helper
                        try:
                            brand_identity = util_functions.generate_brand_identity(
                                service_desc=service_desc,
                                answers=state,
                            )
                        except Exception as e:
                            logging.error(f"Error generating BrandIdentityMap: {e}")
                            worker.write_data(
                                "I had trouble generating your Brand Identity Map. Please try again or contact support.",
                                output="TEXT",
                            )
                            worker.write_eos(output="TEXT")
                            return None

                        # 2) Save BrandIdentityMap to DB
                        try:
                            util_functions.save_brand_identity(project_id, brand_identity)
                        except Exception as e:
                            logging.error(f"Error saving BrandIdentityMap: {e}")
                            worker.write_data(
                                "I generated your Brand Identity Map, but failed to save it. Please contact support.",
                                output="TEXT",
                            )
                            worker.write_eos(output="TEXT")
                            return None

                        # 3) Show summary
                        summary_lines = [
                            "Here is your Brand Identity Map:",
                            f"- Brand name: {brand_identity.get('brand_name')}",
                            f"- Tagline: {brand_identity.get('tagline')}",
                            f"- Mission: {brand_identity.get('mission')}",
                        ]
                        values = brand_identity.get("values") or []
                        if values:
                            summary_lines.append(f"- Values: {', '.join(values)}")
                        uvp = brand_identity.get("uniqueValueProposition")
                        if uvp:
                            summary_lines.append(f"- Unique Value Proposition: {uvp}")

                        worker.write_data("\n".join(summary_lines), output="TEXT")
                        worker.write_data(
                            "\nThis version has been saved. You can refine it later if needed.",
                            output="TEXT",
                        )
                        worker.write_eos(output="TEXT")

                        # Reset state if you want to allow another run
                        self._set_step(worker, 0)
                        self._set_state(worker, {})
                    else:
                        # Unknown step; reset
                        self._set_step(worker, 0)
                        self._set_state(worker, {})

                else:  # Not DONE → field change event: keep latest value
                    data = message.getData()
                    path = data.get("path")
                    if path and worker:
                        timestamp = worker.get_data(path + ".timestamp")
                        new_ts = data.get("timestamp")
                        if timestamp is None or (new_ts is not None and new_ts > timestamp):
                            worker.set_data(
                                path,
                                {
                                    "value": data.get("value"),
                                    "timestamp": new_ts,
                                },
                            )
            return None

        # ---------- Non-EVENT inputs (DEFAULT) ----------

        if message.isBOS():
            # Initialize stream
            if worker:
                worker.set_data(stream, [])
            return None

        if message.isData():
            data = message.getData()
            logging.info(data)
            if worker:
                worker.append_data(stream, data)
            return None

        if message.isEOS():
        # When the user finishes their first message, start the onboarding flow
            step = self._get_step(worker)
            if step == 0:
                # Welcome message
                worker.write_data(WELCOME_TEXT, output="TEXT")

                # Show Step 0: profile form
                self._create_profile_form(worker)

                # Keep step at 0 so the EVENT/DONE handler knows we're in profile step
                self._set_step(worker, 0)
            return None

        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="BRANDING_INTERACTIVE", type=str)
    parser.add_argument("--session", type=str)
    parser.add_argument("--properties", type=str)
    parser.add_argument("--loglevel", default="INFO", type=str)
    parser.add_argument("--serve", type=str)
    parser.add_argument("--platform", type=str, default="default")
    parser.add_argument("--registry", type=str, default="default")

    args = parser.parse_args()

    # set logging
    logging.getLogger().setLevel(args.loglevel.upper())

    # set properties
    properties = {}
    p = args.properties
    if p:
        # decode json
        properties = json.loads(p)

    if args.serve:
        platform = args.platform

        af = AgentFactory(
            _class=BrandingInteractiveAgent,
            _name=args.serve,
            _registry=args.registry,
            platform=platform,
            properties=properties,
        )
        af.wait()
    else:
        a = None
        session = None
        if args.session:
            # join an existing session
            session = Session(cid=args.session)
            a = BrandingInteractiveAgent(
                name=args.name, session=session, properties=properties
            )
        else:
            # create a new session
            session = Session()
            a = BrandingInteractiveAgent(
                name=args.name, session=session, properties=properties
            )

        # wait for session
        if session:
            session.wait()
