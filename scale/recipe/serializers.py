import rest_framework.serializers as serializers

from util.rest import ModelIdSerializer


# Serializers for v6 REST API
class RecipeTypeBaseSerializerV6(ModelIdSerializer):
    """Base serializer for recipe types"""

    name = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    revision_num = serializers.IntegerField()


class RecipeTypeRevisionBaseSerializerV6(ModelIdSerializer):
    """Base serializer for recipe type revisions"""

    recipe_type = ModelIdSerializer()
    revision_num = serializers.IntegerField()


class RecipeTypeRevisionSerializerV6(RecipeTypeRevisionBaseSerializerV6):
    """Serializer for recipe type revisions"""

    definition = serializers.JSONField(default=dict)
    created = serializers.DateTimeField()


class RecipeTypeBaseSerializer(ModelIdSerializer):
    """Converts recipe type model fields to REST output."""
    name = serializers.CharField()
    version = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()


class RecipeTypeSerializer(RecipeTypeBaseSerializer):
    """Converts recipe type model fields to REST output."""
    is_system = serializers.BooleanField()
    is_active = serializers.BooleanField()
    definition = serializers.JSONField(default=dict)
    revision_num = serializers.IntegerField()
    created = serializers.DateTimeField()
    last_modified = serializers.DateTimeField()
    archived = serializers.DateTimeField()

    trigger_rule = ModelIdSerializer()


class RecipeTypeDetailsSerializer(RecipeTypeSerializer):
    """Converts recipe type model fields to REST output."""
    from job.serializers import JobTypeBaseSerializerV5
    from trigger.serializers import TriggerRuleDetailsSerializer

    class RecipeTypeDetailsJobSerializer(JobTypeBaseSerializerV5):
        interface = serializers.JSONField(default=dict)

    trigger_rule = TriggerRuleDetailsSerializer()
    job_types = RecipeTypeDetailsJobSerializer(many=True)


class RecipeTypeRevisionBaseSerializer(ModelIdSerializer):
    """Converts recipe type revision model fields to REST output."""
    recipe_type = ModelIdSerializer()
    revision_num = serializers.IntegerField()


class RecipeTypeRevisionSerializer(RecipeTypeRevisionBaseSerializer):
    """Converts recipe type revision model fields to REST output."""
    definition = serializers.JSONField(default=dict)
    created = serializers.DateTimeField()


class RecipeBaseSerializer(ModelIdSerializer):
    """Converts recipe model fields to REST output."""
    recipe_type = RecipeTypeBaseSerializer()
    recipe_type_rev = ModelIdSerializer()
    event = ModelIdSerializer()


class RecipeSerializer(RecipeBaseSerializer):
    """Converts recipe model fields to REST output."""
    from trigger.serializers import TriggerEventBaseSerializer

    recipe_type_rev = RecipeTypeRevisionBaseSerializer()
    event = TriggerEventBaseSerializer()

    is_superseded = serializers.BooleanField()
    root_superseded_recipe = ModelIdSerializer()
    superseded_recipe = ModelIdSerializer()
    superseded_by_recipe = ModelIdSerializer()

    created = serializers.DateTimeField()
    completed = serializers.DateTimeField()
    superseded = serializers.DateTimeField()
    last_modified = serializers.DateTimeField()


class RecipeJobsSerializer(serializers.Serializer):
    """Converts recipe model fields to REST output."""
    from job.serializers import JobSerializerV5

    job = JobSerializerV5()
    job_name = serializers.CharField(source='node_name')
    is_original = serializers.BooleanField()
    recipe = ModelIdSerializer()


class RecipeJobsDetailsSerializer(RecipeJobsSerializer):
    """Converts related recipe model fields to REST output."""
    from job.serializers import JobRevisionSerializerV5

    job = JobRevisionSerializerV5()


class RecipeDetailsInputSerializer(serializers.Serializer):
    """Converts recipe detail model input fields to REST output"""

    name = serializers.CharField()
    type = serializers.CharField()

    def to_representation(self, obj):
        result = super(RecipeDetailsInputSerializer, self).to_representation(obj)

        value = None
        if 'value' in obj:
            if obj['type'] == 'file':
                value = self.Meta.FILE_SERIALIZER().to_representation(obj['value'])
            elif obj['type'] == 'files':
                value = [self.Meta.FILE_SERIALIZER().to_representation(v) for v in obj['value']]
            else:
                value = obj['value']
        result['value'] = value
        return result

    class Meta:
        from storage.serializers import ScaleFileSerializerV5
        FILE_SERIALIZER = ScaleFileSerializerV5


class RecipeDetailsSerializer(RecipeSerializer):
    """Converts related recipe model fields to REST output."""
    from trigger.serializers import TriggerEventDetailsSerializer

    recipe_type_rev = RecipeTypeRevisionSerializer()
    event = TriggerEventDetailsSerializer()
    input = serializers.JSONField(default=dict)

    jobs = RecipeJobsDetailsSerializer(many=True)

    root_superseded_recipe = RecipeBaseSerializer()
    superseded_recipe = RecipeBaseSerializer()
    superseded_by_recipe = RecipeBaseSerializer()


# TODO: remove this class when REST API v5 is removed
class OldRecipeDetailsSerializer(RecipeSerializer):
    """Converts related recipe model fields to REST output."""
    from trigger.serializers import TriggerEventDetailsSerializer

    recipe_type = RecipeTypeSerializer()
    recipe_type_rev = RecipeTypeRevisionSerializer()
    event = TriggerEventDetailsSerializer()
    data = serializers.JSONField(default=dict, source='input')

    inputs = RecipeDetailsInputSerializer(many=True)
    jobs = RecipeJobsDetailsSerializer(many=True)

    root_superseded_recipe = RecipeBaseSerializer()
    superseded_recipe = RecipeBaseSerializer()
    superseded_by_recipe = RecipeBaseSerializer()
