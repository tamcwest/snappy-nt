"""
This is the module that contains the class for arbitrary precision Manifolds. 

Things to consider:
    1. Building some kind of database that can be loaded to avoid repeating expensive
    computations. I haven't decided how exactly to build and access such a database
    yet.

    2. Perhaps importing functions that actually compute the various invariants from
    numerical input. I.e. make another module and put all the ugly implementation for
    computations there.

"""


import snappy, denominatorsforsnappy
from sage.all import factor, NumberField, QuaternionAlgebra
import math
import functools
import irreducible_subgroups
import misc_functions


class ManifoldAP(snappy.Manifold):
    # Probably make these changeable via a class method at some point.
    # Not sure if this a great pattern to have these as class level attributes.
    # It's possible it should be managed on a per instance level.
    default_starting_prec = 1000
    default_starting_degree = 10
    default_max_prec = 10 ** 6
    default_max_degree = 100
    default_prec_increment = 5000
    default_degree_increment = 5

    def __init__(self, spec=None, delay_computations=False):
        """
        It's worth noting that we store a lot of attributes here. The reason is that a
        lot of them are somewhat expensive to compute. We could alternatively use
        sage's caching capability, but having all these class attributes should make
        them easier to store and reconstruct later.

        Unless delay_computations=True, we try to compute the main arithmetic
        arithmetic invariants with a precision that should only take at most a few
        seconds to succeed or fail. In case one needs to create a lot of these objects
        and the computations will actually meaningfully slow down whatever is being
        done, one may pass in delay_computations=True.
        """
        snappy.Manifold.__init__(self, spec)
        # We store the fields as a sage NumberField objects with a *monic* generating polynomial.
        # Perhaps subclass Sage's NumberField to store all this info?
        # The prec_record variables record whether a given prec and degree was sucessful.
        self.trace_field = None
        self.trace_field_numerical_root = None
        self.trace_field_generators = None
        self.trace_field_prec_record = dict()
        self.invariant_trace_field = None
        self.invariant_trace_field_numerical_root = None
        self.invariant_trace_field_generators = None
        self.invariant_trace_field_prec_record = dict()
        self.quaternion_algebra = None
        self.quaternion_algebra_ramified_places = None
        self.quaternion_algebra_ramified_places_residue_characteristics = None
        self.invariant_quaternion_algebra = None
        self.invariant_quaternion_algebra_ramified_places = None
        self.invariant_quaternion_algebra_ramified_places_residue_characteristics = None
        # denominators will be the empty set if there are no denominators.
        self.denominators = None
        self.denominator_residue_characteristics = None
        if not delay_computations: self.compute_arithmetic_invariants()

    def has_two_torsion_in_homology(self):
        """
        Returns True if there is two-torsion in homology and False if not. This doesn't
        really need arbitrary precision, but it hopefully makes some other code
        cleaner.
        """
        homology = self.homology()
        elementary_divisors = homology.elementary_divisors()
        for divisor in elementary_divisors:
            if divisor % 2 == 0:
                return True
        return False

    def defining_function(self, prec):
        return snappy.snap.polished_holonomy(self, bits_prec=prec)

    def compute_trace_field_fixed_prec(
        self, prec=default_starting_prec, degree=default_starting_degree
    ):
        """
        Note that this will attempt to recompute the trace field even if it is known.
        """
        approx_trace_field = snappy.snap.trace_field_gens(self)
        exact_field_data = approx_trace_field.find_field(
            prec=prec, degree=degree, optimize=True
        )
        # This will override previous calculations with same prec and degree.
        # It's unclear if we want this behavior.
        self.trace_field_prec_record[(prec, degree)] = bool(exact_field_data)
        if exact_field_data is not None:
            self.trace_field = exact_field_data[0]
            self.trace_field_numerical_root = exact_field_data[1]  # An AAN
            self.trace_field_generators = exact_field_data[2]
        return self.trace_field

    def compute_invariant_trace_field_fixed_prec(
        self, prec=default_starting_prec, degree=default_starting_degree
    ):
        """
        This doesn't do anything with homology just yet. Should probably refactor this
        somehow to make invariant and noninvariant trace fields computed through some
        common function.
        Last updated: Aug-29 2020
        """
        approx_invariant_trace_field = snappy.snap.invariant_trace_field_gens(self)
        exact_field_data = approx_invariant_trace_field.find_field(
            prec=prec, degree=degree, optimize=True
        )
        self.invariant_trace_field_prec_record[(prec, degree)] = bool(exact_field_data)
        if exact_field_data is not None:
            self.invariant_trace_field = exact_field_data[0]
            self.invariant_trace_field_numerical_root = exact_field_data[1]  # An AAN
            self.invariant_trace_field_generators = exact_field_data[2]
        return self.invariant_trace_field

    def compute_trace_field(
        self,
        starting_prec=default_starting_prec,
        starting_degree=default_starting_degree,
        prec_increment=default_prec_increment,
        degree_increment=default_degree_increment,
        max_prec=default_max_prec,
        max_degree=default_max_degree,
        verbosity=False,
        use_last_known_failed=False,
    ):
        """
        This is the exact field, returned as a sage NumberField. The exact generators for the
        field are not returned by this method to allow for easier interface with sage. They are
        however computed and stored as an attribute for later use. The method has a
        semicomplicated interface to allow for multiple attempts to find the field. If only one
        attempt is required (e.g. because the requisite precision and degree are known), the
        method compute_trace_field_fixed_prec is probably better and will store the result if
        successful.

        Note that like compute_trace_field_fixed_prec, this method will attempt to
        compute the trace field even it is already known. Use just self.trace_field
        to access previously computed trace fields.

        Something to add: logic for using information when the invariant trace field is
        known. If we just want the number field, we can just check homology and go form
        there, but if we want generators we maybe have to be more careful (or maybe
        not; see MR p.134).

        I think perhaps I should put all the code for computing this in another module
        and just import for this one. I do need to decide on an interface for this one
        though.
         
        Docstring last updated: Aug-27-2020
        """
        prec = starting_prec
        degree = starting_degree
        exact_field = None
        while exact_field == None:
            if verbosity:
                print(
                    str(self) + ":",
                    f"Trying with precision={prec} and degree={degree}",
                )
            exact_field = ManifoldAP.compute_trace_field_fixed_prec(
                self, prec=prec, degree=degree
            )

            if prec == max_prec and degree == max_degree:
                return None
            if prec + prec_increment <= max_prec:
                prec = prec + prec_increment
            else:
                prec = max_prec
            if degree + degree_increment <= max_degree:
                degree = degree + degree_increment
            else:
                degree = max_degree
        return self.trace_field

    def compute_invariant_trace_field(
        self,
        starting_prec=default_starting_prec,
        starting_degree=default_starting_degree,
        prec_increment=default_prec_increment,
        degree_increment=default_degree_increment,
        max_prec=default_max_prec,
        max_degree=default_max_degree,
        verbosity=False,
        use_last_known_failed=False,
    ):
        """
        See docstring for compute_trace_field for more information. This should be
        refactored somehow I think since it's close right now to a copy-paste of the
        method for noninvariant trace fields.
        """
        prec = starting_prec
        degree = starting_degree
        exact_field = None
        while exact_field == None:
            if verbosity:
                print(
                    str(self) + ":",
                    f"Trying with precision={prec} and degree={degree}",
                )
            exact_field = ManifoldAP.compute_invariant_trace_field_fixed_prec(
                self, prec=prec, degree=degree
            )

            if prec == max_prec and degree == max_degree:
                return None
            if prec + prec_increment <= max_prec:
                prec = prec + prec_increment
            else:
                prec = max_prec
            if degree + degree_increment <= max_degree:
                degree = degree + degree_increment
            else:
                degree = max_degree
        return self.invariant_trace_field

    def approximate_trace(self, word):
        """
        Given a word in the generators for the fundamental group, returns an
        ApproximateAlgebraicNumber which is the trace of that element in SL_2(CC). This
        perhaps shouldn't really be a method of the manifold but rather of the group,
        but we can perhaps change this later.
        """

        def trace_defining_func(prec):
            approximate_group = self.defining_function(prec=prec)
            approximate_matrix = approximate_group(word)
            return approximate_matrix.trace()

        return snappy.snap.find_field.ApproximateAlgebraicNumber(trace_defining_func)

    def compute_approximate_hilbert_symbol(self, power=1):
        """
        Somewhat cumbersomly computes a Hilbert symbol as a pair of
        ApproximateAlgebraicNumbers. It's possible I should use the class
        ListOfApproximateAlgebraicNumbers instead.

        power=1 is for noninvariant quaternion algebra, power=2 is for invariant
        quaternion algebra. More generally power=n will give approximate algebraic
        numbers for traces of elements g,h where g is not parabolic and <g,h> is
        irreducible where g,h belong to G^{(n)}, where G is the fundamental group
        (or really the Kleinian group that gives rise to the orbifold). I know of no
        use for any power beyond 2, though.

        Possible improvement: try using the exact expression that are known to trace
        field before getting new elements as AANs. Might not work though since probably
        need a commutator somewhere.

        Last updated: Aug-29 2020
        """
        (word1, word2) = irreducible_subgroups.find_hilbert_symbol_words(
            self.defining_function(prec=ManifoldAP.default_starting_prec)
        )
        first_entry = self.approximate_trace(
            word1
        ) ** 2 - snappy.snap.find_field.ApproximateAlgebraicNumber(4)
        commutator_word = misc_functions.commutator_of_words(word1, word2)
        second_entry = self.approximate_trace(
            commutator_word
        ) - snappy.snap.find_field.ApproximateAlgebraicNumber(2)
        return (first_entry, second_entry)

    def compute_quaternion_algebra_fixed_prec(
        self, prec=default_starting_prec, degree=default_starting_degree
    ):
        """
        If the trace field isn't known, whatever precision and degree are passed here
        are used to try to compute it. If it fails to do so, the entire function fails,
        and will return None. This will try to recompute the quaternion algebra even if
        it is already known, but it won't try to recompute the trace field if it is
        known.

        Possible refactor: Just have one method for computing quaternion algebras from
        ApproximateAlgebraicNumbers. In that case, probably easiest to make another
        module wherein we subclass ApproximateAlgebraicNumber. This could simplify
        other things as well.
        """
        if not self.trace_field:
            self.compute_trace_field_fixed_prec(prec=prec, degree=degree)
        if not self.trace_field:
            return None
        primitive_element = self.trace_field_numerical_root  # An AAN
        (
            approx_first_entry,
            approx_second_entry,
        ) = self.compute_approximate_hilbert_symbol()
        first_entry = primitive_element.express(approx_first_entry, prec=prec)
        second_entry = primitive_element.express(approx_second_entry, prec=prec)
        if first_entry == None or second_entry == None:
            return None
        else:
            self.quaternion_algebra = QuaternionAlgebra(
                self.trace_field, first_entry, second_entry
            )
        if self.quaternion_algebra:
            discriminant_list = list(self.quaternion_algebra.discriminant().factor())
            self.quaternion_algebra_ramified_places = [
                ideal for (ideal, multiplicity) in discriminant_list
            ]
            self.quaternion_algebra_ramified_places_residue_characteristics = list(
                {
                    place.absolute_norm()
                    for place in self.quaternion_algebra_ramified_places
                }
            )
            self.quaternion_algebra_ramified_places_residue_characteristics.sort()
        return self.quaternion_algebra

    def compute_invariant_quaternion_algebra_fixed_prec(
        self, prec=default_starting_prec, degree=default_starting_degree
    ):
        """
        See docstring for compute_quaterion_algebra_fixed_prec. Should try to refactor this
        somehow since it's so similar to the one for the noninvariant quaternion algebra.

        Last updated: Aug-29 2020
        """
        if not self.invariant_trace_field:
            self.compute_invariant_trace_field_fixed_prec(prec=prec, degree=degree)
            if not self.invariant_trace_field:
                return None
        primitive_element = self.invariant_trace_field_numerical_root  # An AAN
        (
            approx_first_entry,
            approx_second_entry,
        ) = self.compute_approximate_hilbert_symbol(power=2)
        first_entry = primitive_element.express(approx_first_entry, prec=prec)
        second_entry = primitive_element.express(approx_second_entry, prec=prec)
        if first_entry == None or second_entry == None:
            return None
        else:
            self.invariant_quaternion_algebra = QuaternionAlgebra(
                self.invariant_trace_field, first_entry, second_entry
            )
        if self.invariant_quaternion_algebra:
            discriminant_list = list(
                self.invariant_quaternion_algebra.discriminant().factor()
            )
            self.invariant_quaternion_algebra_ramified_places = [
                ideal for (ideal, multiplicity) in discriminant_list
            ]
            self.invariant_quaternion_algebra_ramified_places_residue_characteristics = list(
                {
                    place.absolute_norm()
                    for place in self.invariant_quaternion_algebra_ramified_places
                }
            )
            self.invariant_quaternion_algebra_ramified_places_residue_characteristics.sort()
        return self.invariant_quaternion_algebra

    def compute_quaternion_algebra(
        self,
        starting_prec=default_starting_prec,
        starting_degree=default_starting_degree,
        prec_increment=default_prec_increment,
        degree_increment=default_degree_increment,
        max_prec=default_max_prec,
        max_degree=default_max_degree,
        verbosity=False,
        use_last_known_failed=False,
    ):
        """
        Similar to other methods, this will try to compute the algebra even if it is
        already known. It will use a known trace field without recomputing though (see
        the docstring for the compute_quaternion_algebra_fixed_prec).

        We should also maybe try to come up with a unified way to varying the precision
        and degree since this is close to copy and paste of the trace field method.

        To do: Incorporate use_last_known_failed.

        Docstring last updated: Aug-27 2020.
        """
        prec = starting_prec
        degree = starting_degree
        while self.quaternion_algebra == None:
            if verbosity:
                print(
                    str(self) + ":",
                    f"Trying with precision={prec} and degree={degree}",
                )
            ManifoldAP.compute_quaternion_algebra_fixed_prec(
                self, prec=prec, degree=degree
            )

            if prec == max_prec and degree == max_degree:
                return None
            if prec + prec_increment <= max_prec:
                prec = prec + prec_increment
            else:
                prec = max_prec
            if degree + degree_increment <= max_degree:
                degree = degree + degree_increment
            else:
                degree = max_degree
        return self.quaternion_algebra

    def compute_invariant_quaternion_algebra(
        self,
        starting_prec=default_starting_prec,
        starting_degree=default_starting_degree,
        prec_increment=default_prec_increment,
        degree_increment=default_degree_increment,
        max_prec=default_max_prec,
        max_degree=default_max_degree,
        verbosity=False,
        use_last_known_failed=False,
    ):
        """
        See docstrings on compute_quaternion_algebra for more information. This one
        works pretty similarly.
        """
        prec = starting_prec
        degree = starting_degree
        while self.invariant_quaternion_algebra == None:
            if verbosity:
                print(
                    str(self) + ":",
                    f"Trying with precision={prec} and degree={degree}",
                )
            ManifoldAP.compute_invariant_quaternion_algebra_fixed_prec(
                self, prec=prec, degree=degree
            )

            if prec == max_prec and degree == max_degree:
                return None
            if prec + prec_increment <= max_prec:
                prec = prec + prec_increment
            else:
                prec = max_prec
            if degree + degree_increment <= max_degree:
                degree = degree + degree_increment
            else:
                degree = max_degree
        return self.invariant_quaternion_algebra

    def compute_denominators_fixed_prec(
        self, prec=default_starting_prec, degree=default_starting_degree
    ):
        """
        Similar kind of interface to others such a compute_trace_field_fixed_prec
        in that one specifies some precision and degree and the function tries to
        find the denominators for only those parameters.

        This function, as a side-effect, computes the noninvariant trace field of the
        manifold. I think this should be desired more or less because, as far as I
        know, there is basically no way to compute the denominators without computing
        generators for the trace field, which is an expensive operation, so one should
        really try to save the generators if possible.

        This function incidentally computes the residue characteristics of the
        denominators for easy access later.

        It's also worth pointing out that the denominators are returned as a set of
        ideals of a number field. This is different from the behavior in the
        denominatorsforsnappy module that just returns the residue characteristics. We
        could add this as an optional argument at some point though.

        It's possible this shouldn't even really be a method since it depends on
        computing the generators for the trace field. There are no actual hard LLL 
        computations to do here. That is, perhaps it should just refuse to run if
        the trace field generators are not known.

        This function also tries to compute the denominators even if they're already
        known. However, it will use known information about the trace field generators.
        In fact, it needs to know the trace field generators to work.
        """

        if not self.trace_field_generators:
            self.compute_trace_field_fixed_prec(prec=prec, degree=degree)
            if not self.trace_field_generators:
                return None
        denominator_ideals = {
            element.denominator_ideal() for element in self.trace_field_generators
        }
        prime_ideals = set()
        for ideal in denominator_ideals:
            factorization = ideal.factor()
            for element in factorization:
                prime_ideals.add(element[0])
        self.denominators = prime_ideals
        norms = {ideal.absolute_norm() for ideal in prime_ideals}
        self.denominator_residue_characteristics = denominatorsforsnappy.find_prime_factors_in_a_set(
            norms
        )
        return prime_ideals

    def compute_denominators(
        self,
        starting_prec=default_starting_prec,
        starting_degree=default_starting_degree,
        prec_increment=default_prec_increment,
        degree_increment=default_degree_increment,
        max_prec=default_max_prec,
        max_degree=default_max_degree,
        verbosity=False,
        use_last_known_failed=False,
    ):
        """
        As with other methods in this module, this will recompute the denominators even
        if they're known. This should incidentally compute the residue characteristics.
        """
        prec = starting_prec
        degree = starting_degree
        while self.denominators == None:
            if verbosity:
                print(
                    str(self) + ":",
                    f"Trying with precision={prec} and degree={degree}",
                )
            ManifoldAP.compute_denominators_fixed_prec(self, prec=prec, degree=degree)

            if prec == max_prec and degree == max_degree:
                return None
            if prec + prec_increment <= max_prec:
                prec = prec + prec_increment
            else:
                prec = max_prec
            if degree + degree_increment <= max_degree:
                degree = degree + degree_increment
            else:
                degree = max_degree
        return self.denominators

    def is_arithmetic(self):
        """
        This checks whether the manifold (really the Kleinian group) is arithmetic.
        It doesn't itself explicitly compute the necessary invariants if they aren't
        already known.

        For why this works, see MR Theorem 8.3.2 pp.261-262.

        This could be a one-liner, but I think it's clearer this way.
        """
        (
            number_of_complex_places,
            number_of_real_places,
        ) = self.invariant_trace_field.signature()
        number_of_ramified_real_places = len(
            misc_functions.ramified_real_places(self.invariant_quaternion_algebra)
        )
        return (
            number_of_ramified_real_places == number_of_real_places
            and number_of_complex_places == 1
            and self.denominators == set()
        )

    def compute_arithmetic_invariants(
        self,
        starting_prec=default_starting_prec,
        starting_degree=default_starting_degree,
        prec_increment=default_prec_increment,
        degree_increment=default_degree_increment,
        max_prec=default_max_prec,
        max_degree=default_max_degree,
        verbosity=False,
        use_last_known_failed=False,
    ):
        """
        This tries to compute the four basic arithmetic invariants: the two trace
        fields and the two quaternion algebras. There is still no logic for using the
        trace field to compute the invariant trace field or vice versa. This just might
        have to wait for a later version.

        It will also try to compute the other invariants to fill out all the attributes
        of the instance. Right now it's called upon creation of a ManifoldAP instance.
        I think I should change this though to speed up trawling through the census, or
        at least have it as an option.

        There is a little bit of slickness here, namely the first line is just going
        to create a copy of the dictionary of passed in arguments. We have to do this
        at the start or otherwise the other locally defined variables will be in
        locals() and this will mess up our calls to the methods. Speaking of which,
        the invariant_method_pairs list is a list of 2-tuples whose first entry is an
        invariant to be computed and the latter is the method to compute it. It's
        actually important that we don't use self.method (a ``bound method") because
        self will get passed in from the arguments dictionary.

        We could probably make this even more implicit and slick with map or something,
        but let's restrain outselves for now.

        This function also has no return value, and I don't really see a good reason to
        return anything right now.
        """
        arguments = locals().copy()
        invariant_method_pairs = [
            (self.trace_field, ManifoldAP.compute_trace_field),
            (self.quaternion_algebra, ManifoldAP.compute_quaternion_algebra),
            (self.invariant_trace_field, ManifoldAP.compute_invariant_trace_field),
            (
                self.invariant_quaternion_algebra,
                ManifoldAP.compute_invariant_quaternion_algebra,
            ),
        ]
        for (invariant, method) in invariant_method_pairs:
            if not invariant:
                method(**arguments)
        if self.trace_field_generators:
            ManifoldAP.compute_denominators(**arguments)

    def p_arith(self):
        """
        This is so named for the common use case of typing p arith in snap to get the
        arithmetic invariants.

        This function is probably a good argument for subclassing a lot of our objects
        and defining __str__ methods in those classes.
        """
        print('Orbifold name:', self)
        if self.trace_field:
            print('Trace field:', self.trace_field)
            print('\t Signature:', self.trace_field.signature())
            print('\t Discriminant:', self.trace_field.discriminant())

            if self.quaternion_algebra:
                print('Quaternion Algebra:', self.quaternion_algebra)
                print('\t Finite Ramification:', self.quaternion_algebra_ramified_places)
                print('\t Finite Ramification Residue Characteristic:', self.quaternion_algebra_ramified_places_residue_characteristics)
                number_of_ramified_real_places = len(misc_functions.ramified_real_places(self.quaternion_algebra))
                places_grammatical = 'place' if number_of_ramified_real_places == 1 else 'places'
                print('\t Real Ramification:', number_of_ramified_real_places, places_grammatical)
            else:
                print('Quaternion algebra not found.')
        else:
            print('Trace field not found.')
        if self.invariant_trace_field:
            print('Invariant Trace field:', self.invariant_trace_field)
            print('\t Signature:', self.invariant_trace_field.signature())
            print('\t Discriminant:', self.invariant_trace_field.discriminant())
            if self.invariant_quaternion_algebra:
                print('Invariant Quaternion Algebra:', self.invariant_quaternion_algebra)
                print('\t Finite Ramification:', self.invariant_quaternion_algebra_ramified_places)
                print('\t Finite Ramification Residue Characteristic:', self.invariant_quaternion_algebra_ramified_places_residue_characteristics)
                number_of_ramified_real_places = len(misc_functions.ramified_real_places(self.invariant_quaternion_algebra))
                places_grammatical = 'place' if number_of_ramified_real_places == 1 else 'places'
                print('\t Real Ramification:', number_of_ramified_real_places, places_grammatical)
            else:
                print('Invariant quaternion algebra not found.')
        else:
            print('Invariant trace field not found.')
        if self.denominators is None:
            print('Denominators not found (trace field probably not computed)')
        else:
            print('Integer traces:', not bool(self.denominators))
            if len(self.denominators) >= 1:
                print('\t Denominator ideals:', self.denominators)
                print('\t Denominator Residue Characteristics:', self.denominator_residue_characteristics)
        if self.trace_field and self.invariant_quaternion_algebra:
            print('Arithmetic:', bool(self.is_arithmetic()))

        
